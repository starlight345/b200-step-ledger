#include <cuda_runtime.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <string>
#include <vector>

#define CK(x) do { cudaError_t e=(x); if(e!=cudaSuccess){fprintf(stderr,"CUDA %s:%d: %s\n",__FILE__,__LINE__,cudaGetErrorString(e));exit(2);} } while(0)
// This is a controlled memory microbenchmark, NOT a Mamba/LLM compute kernel.
// cg reads bypass L1, making the experiment specific to L2/HBM behavior.
__device__ __forceinline__ uint32_t load_cg(const uint32_t* p){uint32_t v;asm volatile("ld.global.cg.u32 %0, [%1];":"=r"(v):"l"(p):"memory");return v;}
__global__ void update_state(uint32_t* state,size_t n){
 for(size_t i=blockIdx.x*blockDim.x+threadIdx.x;i<n;i+=gridDim.x*blockDim.x){uint32_t v=load_cg(state+i)+1;state[i]=v;}
}
__global__ void read_weights(const uint32_t* weights,size_t n,uint32_t* sink){
 uint32_t v=0;for(size_t i=blockIdx.x*blockDim.x+threadIdx.x;i<n;i+=gridDim.x*blockDim.x)v+=load_cg(weights+i);
 for(int d=16;d>0;d>>=1)v+=__shfl_down_sync(0xffffffff,v,d);
 if((threadIdx.x&31)==0)sink[blockIdx.x*(blockDim.x/32)+(threadIdx.x/32)]=v;
}
__global__ void validate_state(const uint32_t* state,size_t n,uint32_t expected,unsigned int* bad){
 for(size_t i=blockIdx.x*blockDim.x+threadIdx.x;i<n;i+=gridDim.x*blockDim.x)if(state[i]!=expected)atomicAdd(bad,1u);
}
static int grid(size_t n,int sms){return std::max(1,std::min((int)((n+255)/256),sms*16));}
struct Policy{const char* name;bool reserve;bool persist;float ratio;};
int main(int argc,char** argv){
 bool smoke=false,profile=false;for(int i=1;i<argc;++i){if(std::string(argv[i])=="--smoke")smoke=true;if(std::string(argv[i])=="--profile")profile=true;}
 CK(cudaSetDevice(0));cudaDeviceProp p;CK(cudaGetDeviceProperties(&p,0));int rt,driver;CK(cudaRuntimeGetVersion(&rt));CK(cudaDriverGetVersion(&driver));
 size_t freeB,totalB;CK(cudaMemGetInfo(&freeB,&totalB));
 printf("{\"kind\":\"device\",\"name\":\"%s\",\"l2_bytes\":%d,\"persisting_max_bytes\":%d,\"window_max_bytes\":%d,\"sm\":%d,\"cc_major\":%d,\"cc_minor\":%d,\"runtime\":%d,\"driver\":%d,\"free_bytes\":%zu,\"total_bytes\":%zu}\n",p.name,p.l2CacheSize,p.persistingL2CacheMaxSize,p.accessPolicyMaxWindowSize,p.multiProcessorCount,p.major,p.minor,rt,driver,freeB,totalB);fflush(stdout);
 if(p.persistingL2CacheMaxSize<=0||p.accessPolicyMaxWindowSize<=0){fprintf(stderr,"No persisting L2 support; stop without inventing a comparison.\n");return 3;}
 cudaStream_t stream;CK(cudaStreamCreateWithFlags(&stream,cudaStreamNonBlocking));
 // Granite-4.0-h-tiny's measured state footprint: 806400 B/layer/sequence, 36 state layers.
 // uint32 increments preserve exact correctness across all policies; this is a shape proxy.
 const int layers=36;const size_t oneSequenceLayerBytes=806400;
 const size_t reserveBytes=std::min((size_t)p.persistingL2CacheMaxSize,(size_t)p.l2CacheSize*3/4);
 std::vector<int> batches=smoke?std::vector<int>{1}:std::vector<int>{1,2,4,8};
 std::vector<int> pollutionMiB=smoke?std::vector<int>{64}:std::vector<int>{0,8,64,256};
 uint32_t* sink;unsigned int* bad;CK(cudaMalloc(&sink,p.multiProcessorCount*16*8*sizeof(uint32_t)));CK(cudaMalloc(&bad,sizeof(unsigned int)));
 for(int B:batches)for(int gap:pollutionMiB){
  size_t stateLayerBytes=oneSequenceLayerBytes*B,stateBytes=stateLayerBytes*layers;
  size_t weightLayerBytes=(size_t)gap*1024*1024,weightBytes=weightLayerBytes*layers;
  CK(cudaMemGetInfo(&freeB,&totalB));if(freeB<stateBytes+weightBytes+2ull*1024*1024*1024){fprintf(stderr,"Insufficient free memory for cell B=%d gap=%d; stop.\n",B,gap);return 4;}
  uint32_t *state,*weight;CK(cudaMalloc(&state,stateBytes));CK(cudaMalloc(&weight,std::max(weightBytes,(size_t)4)));CK(cudaMemset(weight,1,std::max(weightBytes,(size_t)4)));
  size_t windowBytes=std::min(stateBytes,(size_t)p.accessPolicyMaxWindowSize);
  float tuned=std::min(1.0,(double)reserveBytes/windowBytes);
  std::vector<Policy> policies={{"default",false,false,0},{"reserved_normal",true,false,0},{"persist_state_1",true,true,1},{"persist_state_tuned",true,true,tuned}};
  for(int pass=0;pass<(smoke?1:3);pass++){
   std::vector<int> order=pass%2?std::vector<int>{3,2,1,0}:std::vector<int>{0,1,2,3};
   // Pass 3 rotates the first policy, so default is not always a cold-start endpoint.
   if(pass==2)order={1,0,3,2};
   for(int pi:order){
    const auto pol=policies[pi];CK(cudaStreamSynchronize(stream));CK(cudaCtxResetPersistingL2Cache());
    CK(cudaDeviceSetLimit(cudaLimitPersistingL2CacheSize,pol.reserve?reserveBytes:0));size_t actualReserve;CK(cudaDeviceGetLimit(&actualReserve,cudaLimitPersistingL2CacheSize));
    cudaStreamAttrValue attr{};attr.accessPolicyWindow.base_ptr=state;attr.accessPolicyWindow.num_bytes=pol.persist?windowBytes:0;
    attr.accessPolicyWindow.hitRatio=pol.ratio;attr.accessPolicyWindow.hitProp=cudaAccessPropertyPersisting;attr.accessPolicyWindow.missProp=cudaAccessPropertyStreaming;
    CK(cudaStreamSetAttribute(stream,cudaStreamAttributeAccessPolicyWindow,&attr));
    CK(cudaMemsetAsync(state,0,stateBytes,stream));CK(cudaStreamSynchronize(stream));
    cudaGraph_t graph;cudaGraphExec_t executable;CK(cudaStreamBeginCapture(stream,cudaStreamCaptureModeGlobal));
    for(int layer=0;layer<layers;layer++){
     update_state<<<grid(stateLayerBytes/4,p.multiProcessorCount),256,0,stream>>>(state+layer*(stateLayerBytes/4),stateLayerBytes/4);
     if(weightBytes)read_weights<<<grid(weightLayerBytes/4,p.multiProcessorCount),256,0,stream>>>(weight+layer*(weightLayerBytes/4),weightLayerBytes/4,sink);
    }
    CK(cudaGetLastError());CK(cudaStreamEndCapture(stream,&graph));
    // Stream hints are not relied on implicitly after graph capture. Stamp the
    // access window explicitly on every kernel node for reproducible graph behavior.
    size_t count=0;CK(cudaGraphGetNodes(graph,nullptr,&count));std::vector<cudaGraphNode_t> nodes(count);CK(cudaGraphGetNodes(graph,nodes.data(),&count));
    cudaKernelNodeAttrValue nodeAttr{};nodeAttr.accessPolicyWindow=attr.accessPolicyWindow;
    for(auto node:nodes){cudaGraphNodeType type;CK(cudaGraphNodeGetType(node,&type));if(type==cudaGraphNodeTypeKernel)CK(cudaGraphKernelNodeSetAttribute(node,cudaKernelNodeAttributeAccessPolicyWindow,&nodeAttr));}
    CK(cudaGraphInstantiate(&executable,graph,0));
    const int warm=profile?1:10;for(int i=0;i<warm;i++)CK(cudaGraphLaunch(executable,stream));CK(cudaStreamSynchronize(stream));
    cudaEvent_t start,end;CK(cudaEventCreate(&start));CK(cudaEventCreate(&end));
    CK(cudaEventRecord(start,stream));const int pilot=profile?1:5;for(int i=0;i<pilot;i++)CK(cudaGraphLaunch(executable,stream));CK(cudaEventRecord(end,stream));CK(cudaEventSynchronize(end));float pilotMs;CK(cudaEventElapsedTime(&pilotMs,start,end));
    int iterations=profile?1:std::min(10000,std::max(10,(int)std::ceil((smoke?30.0:200.0)/(pilotMs/pilot))));
    CK(cudaEventRecord(start,stream));auto wallStart=std::chrono::steady_clock::now();for(int i=0;i<iterations;i++)CK(cudaGraphLaunch(executable,stream));CK(cudaEventRecord(end,stream));CK(cudaEventSynchronize(end));auto wallEnd=std::chrono::steady_clock::now();float elapsed;CK(cudaEventElapsedTime(&elapsed,start,end));
    CK(cudaMemsetAsync(bad,0,sizeof(unsigned int),stream));validate_state<<<grid(stateBytes/4,p.multiProcessorCount),256,0,stream>>>(state,stateBytes/4,warm+pilot+iterations,bad);unsigned int errors;CK(cudaMemcpyAsync(&errors,bad,sizeof(errors),cudaMemcpyDeviceToHost,stream));CK(cudaStreamSynchronize(stream));
    printf("{\"kind\":\"trial\",\"workload\":\"granite_state_shape_memory_proxy\",\"B\":%d,\"layers\":%d,\"state_bytes\":%zu,\"weight_bytes\":%zu,\"pollution_mib_per_layer\":%d,\"logical_state_read_bytes\":%zu,\"logical_state_write_bytes\":%zu,\"logical_weight_read_bytes\":%zu,\"pass\":%d,\"policy\":\"%s\",\"reserve_bytes\":%zu,\"window_bytes\":%zu,\"window_coverage\":%.8f,\"hit_ratio_hint\":%.8f,\"warm_iterations\":%d,\"pilot_iterations\":%d,\"iterations\":%d,\"step_ms\":%.8f,\"wall_ms\":%.5f,\"validation_errors\":%u,\"state_ptr\":\"%p\",\"weights_ptr\":\"%p\"}\n",B,layers,stateBytes,weightBytes,gap,stateBytes,stateBytes,weightBytes,pass,pol.name,actualReserve,pol.persist?windowBytes:0,pol.persist?(double)windowBytes/stateBytes:0,pol.ratio,warm,pilot,iterations,elapsed/iterations,std::chrono::duration<double,std::milli>(wallEnd-wallStart).count(),errors,(void*)state,(void*)weight);fflush(stdout);
    CK(cudaEventDestroy(start));CK(cudaEventDestroy(end));CK(cudaGraphExecDestroy(executable));CK(cudaGraphDestroy(graph));
    if(errors){fprintf(stderr,"Correctness failure; stop.\n");return 5;}
   }
  }
  cudaStreamAttrValue reset{};reset.accessPolicyWindow.num_bytes=0;CK(cudaStreamSetAttribute(stream,cudaStreamAttributeAccessPolicyWindow,&reset));CK(cudaStreamSynchronize(stream));CK(cudaCtxResetPersistingL2Cache());CK(cudaFree(state));CK(cudaFree(weight));
 }
 CK(cudaDeviceSetLimit(cudaLimitPersistingL2CacheSize,0));CK(cudaFree(sink));CK(cudaFree(bad));CK(cudaStreamDestroy(stream));return 0;
}

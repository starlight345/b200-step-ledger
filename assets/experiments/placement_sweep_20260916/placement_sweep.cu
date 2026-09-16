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

__device__ __forceinline__ uint32_t load_cg(const uint32_t* p){
  uint32_t v; asm volatile("ld.global.cg.u32 %0, [%1];":"=r"(v):"l"(p):"memory"); return v;
}
__global__ void read_object(const uint32_t* x,size_t n,uint32_t* sink){
  uint32_t v=0;
  for(size_t i=blockIdx.x*blockDim.x+threadIdx.x;i<n;i+=gridDim.x*blockDim.x) v+=load_cg(x+i);
  for(int d=16;d>0;d>>=1) v+=__shfl_down_sync(0xffffffff,v,d);
  if((threadIdx.x&31)==0) sink[blockIdx.x*(blockDim.x/32)+(threadIdx.x/32)]=v;
}
__global__ void update_state(uint32_t* x,size_t n){
  for(size_t i=blockIdx.x*blockDim.x+threadIdx.x;i<n;i+=gridDim.x*blockDim.x) x[i]=load_cg(x+i)+1;
}
__global__ void validate_state(const uint32_t* x,size_t n,uint32_t expected,unsigned int* bad){
  for(size_t i=blockIdx.x*blockDim.x+threadIdx.x;i<n;i+=gridDim.x*blockDim.x) if(x[i]!=expected) atomicAdd(bad,1u);
}
static int grid(size_t n,int sms){return std::max(1,std::min((int)((n+255)/256),sms*16));}
struct Policy{const char* name;int target;}; // -1 default, -2 reserve-only, 0 W, 1 KV, 2 state

int main(int argc,char** argv){
  CK(cudaSetDevice(0));
  cudaDeviceProp p; CK(cudaGetDeviceProperties(&p,0));
  size_t freeB,totalB; CK(cudaMemGetInfo(&freeB,&totalB));
  const size_t MiB=1024ull*1024ull, objectBytes=(argc>1?std::stoull(argv[1]):64)*MiB;
  const int layers=argc>2?std::atoi(argv[2]):36;
  const size_t layerBytes=objectBytes/layers/256*256;
  const size_t usedBytes=layerBytes*layers;
  const size_t reserveBytes=std::min((size_t)p.persistingL2CacheMaxSize,(size_t)p.l2CacheSize*3/4);
  printf("{\"kind\":\"device\",\"name\":\"%s\",\"l2_bytes\":%d,\"persisting_max_bytes\":%d,\"window_max_bytes\":%d,\"reserve_bytes\":%zu,\"object_bytes\":%zu,\"layers\":%d,\"sm\":%d,\"free_bytes\":%zu,\"total_bytes\":%zu}\n",p.name,p.l2CacheSize,p.persistingL2CacheMaxSize,p.accessPolicyMaxWindowSize,reserveBytes,usedBytes,layers,p.multiProcessorCount,freeB,totalB); fflush(stdout);
  if(!reserveBytes || !p.accessPolicyMaxWindowSize){fprintf(stderr,"Equal target does not fit the supported persisting window.\n");return 3;}

  uint32_t *weight,*kv,*state,*sink; unsigned int* bad;
  CK(cudaMalloc(&weight,usedBytes)); CK(cudaMalloc(&kv,usedBytes)); CK(cudaMalloc(&state,usedBytes));
  CK(cudaMalloc(&sink,p.multiProcessorCount*16*8*sizeof(uint32_t))); CK(cudaMalloc(&bad,sizeof(unsigned int)));
  CK(cudaMemset(weight,1,usedBytes)); CK(cudaMemset(kv,2,usedBytes));
  cudaStream_t stream; CK(cudaStreamCreateWithFlags(&stream,cudaStreamNonBlocking));
  const char* orderNames[]={"WKS","WSK","KWS","KSW","SWK","SKW"};
  const int orders[6][3]={{0,1,2},{0,2,1},{1,0,2},{1,2,0},{2,0,1},{2,1,0}};
  std::vector<Policy> policies={{"default",-1},{"reserved_normal",-2},{"persist_weight",0},{"persist_kv",1},{"persist_state",2}};

  for(int oi=0;oi<6;oi++) for(int pass=0;pass<3;pass++){
    int starts[3]={0,3,1}; int start=starts[pass];
    for(int po=0;po<5;po++){
      const Policy pol=policies[(start+po)%5];
      CK(cudaStreamSynchronize(stream)); CK(cudaCtxResetPersistingL2Cache());
      CK(cudaDeviceSetLimit(cudaLimitPersistingL2CacheSize,pol.target==-1?0:reserveBytes));
      size_t actualReserve=0; CK(cudaDeviceGetLimit(&actualReserve,cudaLimitPersistingL2CacheSize));
      void* bases[3]={(void*)weight,(void*)kv,(void*)state};
      cudaStreamAttrValue attr{};
      attr.accessPolicyWindow.base_ptr=pol.target>=0?bases[pol.target]:nullptr;
      attr.accessPolicyWindow.num_bytes=pol.target>=0?std::min(usedBytes,(size_t)p.accessPolicyMaxWindowSize):0;
      attr.accessPolicyWindow.hitRatio=pol.target>=0?std::min(1.0f,(float)reserveBytes/attr.accessPolicyWindow.num_bytes):0.0f;
      attr.accessPolicyWindow.hitProp=cudaAccessPropertyPersisting;
      attr.accessPolicyWindow.missProp=cudaAccessPropertyStreaming;
      CK(cudaStreamSetAttribute(stream,cudaStreamAttributeAccessPolicyWindow,&attr));
      CK(cudaMemsetAsync(state,0,usedBytes,stream)); CK(cudaStreamSynchronize(stream));

      cudaGraph_t graph; cudaGraphExec_t executable;
      CK(cudaStreamBeginCapture(stream,cudaStreamCaptureModeGlobal));
      for(int layer=0;layer<layers;layer++) for(int q=0;q<3;q++){
        int obj=orders[oi][q]; size_t off=(size_t)layer*(layerBytes/4);
        if(obj==0) read_object<<<grid(layerBytes/4,p.multiProcessorCount),256,0,stream>>>(weight+off,layerBytes/4,sink);
        if(obj==1) read_object<<<grid(layerBytes/4,p.multiProcessorCount),256,0,stream>>>(kv+off,layerBytes/4,sink);
        if(obj==2) update_state<<<grid(layerBytes/4,p.multiProcessorCount),256,0,stream>>>(state+off,layerBytes/4);
      }
      CK(cudaGetLastError()); CK(cudaStreamEndCapture(stream,&graph));
      size_t nodeCount=0; CK(cudaGraphGetNodes(graph,nullptr,&nodeCount)); std::vector<cudaGraphNode_t> nodes(nodeCount); CK(cudaGraphGetNodes(graph,nodes.data(),&nodeCount));
      cudaKernelNodeAttrValue nodeAttr{}; nodeAttr.accessPolicyWindow=attr.accessPolicyWindow;
      for(auto node:nodes){cudaGraphNodeType t;CK(cudaGraphNodeGetType(node,&t));if(t==cudaGraphNodeTypeKernel)CK(cudaGraphKernelNodeSetAttribute(node,cudaKernelNodeAttributeAccessPolicyWindow,&nodeAttr));}
      CK(cudaGraphInstantiate(&executable,graph,0));

      const int warm=10,pilot=5; for(int i=0;i<warm;i++) CK(cudaGraphLaunch(executable,stream)); CK(cudaStreamSynchronize(stream));
      cudaEvent_t a,b; CK(cudaEventCreate(&a)); CK(cudaEventCreate(&b));
      CK(cudaEventRecord(a,stream)); for(int i=0;i<pilot;i++) CK(cudaGraphLaunch(executable,stream)); CK(cudaEventRecord(b,stream)); CK(cudaEventSynchronize(b));
      float pilotMs; CK(cudaEventElapsedTime(&pilotMs,a,b));
      int iterations=std::min(10000,std::max(10,(int)std::ceil(250.0/(pilotMs/pilot))));
      CK(cudaEventRecord(a,stream)); auto wallA=std::chrono::steady_clock::now(); for(int i=0;i<iterations;i++) CK(cudaGraphLaunch(executable,stream)); CK(cudaEventRecord(b,stream)); CK(cudaEventSynchronize(b)); auto wallB=std::chrono::steady_clock::now();
      float elapsed; CK(cudaEventElapsedTime(&elapsed,a,b));
      CK(cudaMemsetAsync(bad,0,sizeof(unsigned int),stream)); validate_state<<<grid(usedBytes/4,p.multiProcessorCount),256,0,stream>>>(state,usedBytes/4,warm+pilot+iterations,bad);
      unsigned int errors=0; CK(cudaMemcpyAsync(&errors,bad,sizeof(errors),cudaMemcpyDeviceToHost,stream)); CK(cudaStreamSynchronize(stream));
      printf("{\"kind\":\"trial\",\"order\":\"%s\",\"pass\":%d,\"policy\":\"%s\",\"target\":%d,\"object_bytes\":%zu,\"logical_weight_read_bytes\":%zu,\"logical_kv_read_bytes\":%zu,\"logical_state_read_bytes\":%zu,\"logical_state_write_bytes\":%zu,\"ledger_score_weight\":1.0,\"ledger_score_kv\":1.0,\"ledger_score_state\":2.0,\"reserve_bytes\":%zu,\"window_bytes\":%zu,\"warm_iterations\":%d,\"pilot_iterations\":%d,\"iterations\":%d,\"step_ms\":%.8f,\"wall_ms\":%.5f,\"validation_errors\":%u}\n",orderNames[oi],pass,pol.name,pol.target,usedBytes,usedBytes,usedBytes,usedBytes,usedBytes,actualReserve,attr.accessPolicyWindow.num_bytes,warm,pilot,iterations,elapsed/iterations,std::chrono::duration<double,std::milli>(wallB-wallA).count(),errors); fflush(stdout);
      CK(cudaEventDestroy(a)); CK(cudaEventDestroy(b)); CK(cudaGraphExecDestroy(executable)); CK(cudaGraphDestroy(graph));
      if(errors){fprintf(stderr,"Correctness failure.\n");return 5;}
    }
  }
  cudaStreamAttrValue reset{}; reset.accessPolicyWindow.num_bytes=0; CK(cudaStreamSetAttribute(stream,cudaStreamAttributeAccessPolicyWindow,&reset)); CK(cudaStreamSynchronize(stream)); CK(cudaCtxResetPersistingL2Cache()); CK(cudaDeviceSetLimit(cudaLimitPersistingL2CacheSize,0));
  CK(cudaFree(weight)); CK(cudaFree(kv)); CK(cudaFree(state)); CK(cudaFree(sink)); CK(cudaFree(bad)); CK(cudaStreamDestroy(stream)); return 0;
}

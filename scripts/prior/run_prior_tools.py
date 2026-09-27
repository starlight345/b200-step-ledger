#!/usr/bin/env python3
"""Run the actual prior-work tools on the R1 decode workloads and record their predictions.

  GenZ       decode_moddeling() with a ModelConfig for each SmolLM model (num_ffi=2 / silu, as GenZ writes
             Llama) on a system dict for this GPU. DRAM bytes = the operand bytes GenZ charges at off-chip
             bandwidth (MB = 2^20): every operator's activations, weights and outputs, except the score
             matrix it pins on chip in decode. Its 'Total Data (MB)' (which includes that) is kept alongside.
  LLMCompass Matmul / BatchedMatmul operators from its software_model, driven with the exact decode operator
             list (q,k,v,o, gate,up,down per layer, GQA attention per KV group, LM head) on a device built from
             its GA102 template with this GPU's numbers. Latency = its heuristic-GPU simulation. Bytes = its
             GEMV I/O accounting (M*K + N*K + M*N) * word size, operand sizes for the batched matmuls.
Hardware numbers given to both tools are the SAME measured ones our models use: DRAM 1.230 TB/s
(streaming, l2policy_bench calibration), L2 96 MiB, 110 SMs at 2.37 GHz, 48 GB.

Usage (GPU host venv): python run_prior_tools.py <thirdparty_dir> <hf_config_dir> > prior_tools_r1.json
"""
import copy, json, os, sys

TP, HFD = sys.argv[1], sys.argv[2]
TOOLS = (sys.argv[3] if len(sys.argv) > 3 else 'genz,llmcompass').split(',')
RUNS = [('SmolLM-135M', 1), ('SmolLM-135M', 8), ('SmolLM-360M', 1)]
CONTEXT = 512
B_DRAM_GBs = 1230.0
out = {'genz': {}, 'llmcompass': {}, 'genz_latency_ms': {}, 'llmcompass_latency_ms': {}}

# ------------------------------------------------------------------ GenZ (needs Python >= 3.10)
if 'genz' in TOOLS:
  sys.path.insert(0, os.path.join(TP, 'GenZ-LLM-Analyzer'))
  from GenZ import decode_moddeling
  from GenZ.Models.default_models import ModelConfig
for name, B in (RUNS if 'genz' in TOOLS else []):
    c = json.load(open(os.path.join(HFD, name + '.json')))
    mc = ModelConfig(model=name, vocab_size=c['vocab_size'], hidden_size=c['hidden_size'],
                     intermediate_size=c['intermediate_size'], num_ffi=2, num_decoder_layers=c['num_hidden_layers'],
                     num_attention_heads=c['num_attention_heads'], num_key_value_heads=c['num_key_value_heads'],
                     head_dim=c['hidden_size'] // c['num_attention_heads'], hidden_act='silu', max_model_len=2048)
    r = decode_moddeling(model=mc, batch_size=B, input_tokens=CONTEXT, output_tokens=1,
                         system_name={'Flops': 250, 'Memory_size': 48, 'Memory_BW': B_DRAM_GBs, 'ICN': 64,
                                      'real_values': True}, bits='bf16')
    key = f'{name}/B{B}'
    # ModdelingOutput is a dict: fields are keys (attribute access returns the class defaults)
    df, sm = r['model_df'], r['summary_table']
    # off-chip bytes = what GenZ's memory time charges at off-chip bandwidth: every operand, minus the two
    # tensors decode pins on chip (intermediate_on_chip=True: Logit output, Attend input_a = the score matrix)
    off, mult = 0.0, 1
    for i in range(len(df)):
        t = df.loc[i, 'Op Type']
        if t == 'Repeat': mult *= df.loc[i, 'Dimension']; continue
        if t == 'EndRepeat': mult /= df.loc[i, 'Dimension']; continue
        a, w, o = (df.loc[i, f'{c} (MB)'] for c in ('Input_a', 'Input_w', 'Output'))
        if t == 'Logit': o = 0
        if t == 'Attend': a = 0
        off += (a + w + o) * mult
    out['genz'][key] = off * 2**20
    out['genz_latency_ms'][key] = float(r['Latency'])
    out.setdefault('genz_detail', {})[key] = {
        'total_data_bytes': float(sm['Total Data (MB)'].values[0]) * 2**20,
        'weights_bytes': float(sm['Total Weights (MB)'].values[0]) * 2**20,
        'kv_bytes': float(sm['KV Cache (MB)'].values[0]) * 2**20,
        'ops': [str(x) for x in df['Layer Name'].tolist()]}

# ------------------------------------------------------------------ LLMCompass
if 'llmcompass' not in TOOLS:
    print(json.dumps(out, indent=1)); sys.exit(0)
sys.path.insert(0, os.path.join(TP, 'LLMCompass'))
os.chdir(os.path.join(TP, 'LLMCompass'))
from design_space_exploration.dse import read_architecture_template, template_to_system
from software_model.matmul import Matmul, BatchedMatmul
from software_model.utils import Tensor, data_type_dict
spec = read_architecture_template('configs/ga102_template.json')
spec = copy.deepcopy(spec)
spec['device_count'] = 1
d = spec['device']
d['frequency_Hz'] = 2370e6
d['compute_chiplet']['core_count'] = 110
d['compute_chiplet']['physical_core_count'] = 110
io = d['io']
io['global_buffer_MB'] = 96
io['physical_global_buffer_MB'] = 96
bw_now = io['memory_channel_active_count'] * io['pin_count_per_channel'] * io['bandwidth_per_pin_bit'] / 8
io['bandwidth_per_pin_bit'] *= (B_DRAM_GBs * 1e9) / bw_now
d['memory']['total_capacity_GB'] = 48
system = template_to_system(spec)
dev = system.device
fp16 = data_type_dict['fp16']

def mm(M, K, N):
    op = Matmul(fp16); _ = op(Tensor([M, K], fp16), Tensor([K, N], fp16))
    lat = op.compile_and_simulate(dev, 'heuristic-GPU')
    return lat, (M * K + N * K + M * N) * fp16.word_size

def bmm(bs, M, K, N):
    op = BatchedMatmul(fp16); _ = op(Tensor([bs, M, K], fp16), Tensor([bs, K, N], fp16))
    lat = op.compile_and_simulate(dev, 'heuristic-GPU')
    return lat, bs * (M * K + K * N + M * N) * fp16.word_size

for name, B in RUNS:
    c = json.load(open(os.path.join(HFD, name + '.json')))
    H, I, L = c['hidden_size'], c['intermediate_size'], c['num_hidden_layers']
    nh, kvh = c['num_attention_heads'], c['num_key_value_heads']; hd = H // nh; g = nh // kvh
    lat = byt = 0.0
    for M, K, N in ((B, H, H), (B, H, kvh * hd), (B, H, kvh * hd), (B, H, H), (B, H, I), (B, H, I), (B, I, H)):
        l, b = mm(M, K, N); lat += l * L; byt += b * L
    for bs, M, K, N in ((B * kvh, g, hd, CONTEXT), (B * kvh, g, CONTEXT, hd)):   # QK^T and AV per KV group
        l, b = bmm(bs, M, K, N); lat += l * L; byt += b * L
    l, b = mm(B, H, c['vocab_size']); lat += l; byt += b                      # LM head
    key = f'{name}/B{B}'
    out['llmcompass'][key] = byt
    out['llmcompass_latency_ms'][key] = lat * 1e3

print(json.dumps(out, indent=1))

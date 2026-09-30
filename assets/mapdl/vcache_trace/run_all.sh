#!/bin/bash
B=/TOOLS/SYNOPSYS/RedHawk-SC_Electrothermal_Linux64e8_Y-2026.03-SP2
export AWP_ROOT261=$B/solver/Mechanical_Engine/v261; export ANSYS261_DIR=$AWP_ROOT261/ansys
export ANSYSLIC_DIR=$B/shared_files/licensing; export ANSYS_SYSDIR=linx64
cd ~/ectc_thermal/vcache_trace
: > results.txt
one() { f=$1; rm -rf run_$f; mkdir run_$f; cd run_$f; cp ../$f.dat .;
  S=$(date +%s); $ANSYS261_DIR/bin/mapdl -b -np 1 -j $f -i $f.dat -o $f.out >/dev/null 2>&1; E=$(date +%s)
  echo "$f $((E-S))s $(grep -h RESULT summary.txt 2>/dev/null) errors=$(grep -c "\*\*\* ERROR" $f.out)" >> ../results.txt; }
export -f one; export ANSYS261_DIR
printf "%s\n" lid_s1_phi90_w1000us lid_s1_phi90_w200us lid_s1_phi90_w20us lid_s4_phi90_exact lid_s4_phiU_exact lid_s4_phi90_w1000us prod_s1_phi90_w1000us prod_s1_phi90_w200us prod_s1_phi90_w20us prod_s4_phi90_exact prod_s4_phiU_exact prod_s4_phi90_w1000us | xargs -P 4 -I{} bash -c "one {}"
echo DONE >> results.txt

#!/bin/bash
B=/TOOLS/SYNOPSYS/RedHawk-SC_Electrothermal_Linux64e8_Y-2026.03-SP2
export AWP_ROOT261=$B/solver/Mechanical_Engine/v261; export ANSYS261_DIR=$AWP_ROOT261/ansys
export ANSYSLIC_DIR=$B/shared_files/licensing; export ANSYS_SYSDIR=linx64
cd ~/ectc_thermal/vcache_sched
: > run_phi.txt
one() { f=$1; rm -rf run_$f; mkdir run_$f; cd run_$f; cp ../$f.dat .;
  S=$(date +%s); $ANSYS261_DIR/bin/mapdl -b -np 1 -j $f -i $f.dat -o $f.out >/dev/null 2>&1; E=$(date +%s)
  echo "$f $((E-S))s $(grep -h RESULT summary.txt 2>/dev/null) errors=$(grep -c "\*\*\* ERROR" $f.out)" >> ../run_phi.txt; }
export -f one; export ANSYS261_DIR
printf "%s\n" static_phi50 static_phi70 lid_static_phi50 lid_static_phi70 lid_static_phiU lid_s0_phiU lid_s0_phi50 lid_s0_phi70 lid_s1_phi50 lid_s1_phi70 prod_s0_phiU prod_s0_phi50 prod_s0_phi70 prod_s0_phi90 prod_s1_phi50 prod_s1_phi70 | xargs -P 8 -I{} bash -c "one {}"
echo DONE >> run_phi.txt

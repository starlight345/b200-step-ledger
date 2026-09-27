#!/bin/bash
B=/TOOLS/SYNOPSYS/RedHawk-SC_Electrothermal_Linux64e8_Y-2026.03-SP2
export AWP_ROOT261=$B/solver/Mechanical_Engine/v261; export ANSYS261_DIR=$AWP_ROOT261/ansys
export ANSYSLIC_DIR=$B/shared_files/licensing; export ANSYS_SYSDIR=linx64
cd ~/ectc_thermal/vcache_sched
: > results.txt
one() { f=$1; rm -rf run_$f; mkdir run_$f; cd run_$f; cp ../$f.dat .;
  S=$(date +%s); $ANSYS261_DIR/bin/mapdl -b -np 1 -j $f -i $f.dat -o $f.out >/dev/null 2>&1; E=$(date +%s)
  echo "$f $((E-S))s $(grep -h RESULT summary.txt 2>/dev/null) errors=$(grep -c "\*\*\* ERROR" $f.out)" >> ../results.txt; }
export -f one; export ANSYS261_DIR
printf "%s\n" static_phiU static_phi90 s1_verify s1_phiU s1_phi90 s3_phi90 | xargs -P 4 -I{} bash -c "one {}"
echo DONE >> results.txt

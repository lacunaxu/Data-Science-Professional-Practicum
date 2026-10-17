#!/bin/bash
set -e

# ====== settings ======
BIN=./conv_step1
OUTDIR=output_pic
STEPDIR=$OUTDIR/step1
LOG=$STEPDIR/timing_step1.log

# your original image files (jpg/webp)
SOURCES=("pic1.jpg" "pic2.webp" "pic3.webp")

# sizes and kernels
MS=(256 512 1024)
NS=(3 5 7)
FILTERS=("blur" "sharpen" "laplacian")

# ====== prepare folders ======
mkdir -p "$STEPDIR/pgm" "$STEPDIR/png" "$OUTDIR/step2" "$OUTDIR/step3"
: > "$LOG"

# ====== build binary if missing ======
if [ ! -f "$BIN" ]; then
  echo "conv_step1 not found, compiling..."
  gcc -O2 conv_step1.c -o conv_step1
fi

# ====== 1) convert original images to grayscale pgm (P2) ======
echo "== Converting input images to PGM ==" | tee -a "$LOG"
for src in "${SOURCES[@]}"; do
  base="${src%.*}"   # pic1 / pic2 / pic3
  for M in "${MS[@]}"; do
    pgm_in="$STEPDIR/pgm/${base}_${M}.pgm"
    magick "$src" -colorspace Gray -resize ${M}x${M}\! -compress none -depth 8 "$pgm_in"
  done
done

# ====== 2) run 81 step1 convolutions ======
echo "== Running Step1 convolutions (81 runs) ==" | tee -a "$LOG"
for src in "${SOURCES[@]}"; do
  base="${src%.*}"
  for M in "${MS[@]}"; do
    in="$STEPDIR/pgm/${base}_${M}.pgm"
    for N in "${NS[@]}"; do
      for f in "${FILTERS[@]}"; do
        out_pgm="$STEPDIR/pgm/out_${base}_${M}_${f}_${N}.pgm"
        out_png="$STEPDIR/png/out_${base}_${M}_${f}_${N}.png"

        echo "[$(date '+%H:%M:%S')] $BIN $in $out_pgm $f $N" | tee -a "$LOG"
        $BIN "$in" "$out_pgm" "$f" "$N" | tee -a "$LOG"

        # make png preview (easier to open)
        magick "$out_pgm" "$out_png"
      done
    done
  done
done

echo "DONE. Step1 outputs in: $STEPDIR"
echo "PGM: $STEPDIR/pgm"
echo "PNG: $STEPDIR/png"
echo "Log: $LOG"

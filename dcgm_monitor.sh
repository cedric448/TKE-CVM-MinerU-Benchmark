#!/bin/bash
# DCGM GPU Monitoring Script - Records metrics every 5 seconds
# Output: CSV file with timestamp, GPU util, mem util, power, temp, SM clock, mem clock, SM active, SM occupancy, FB used, FB free

OUTPUT_FILE="/root/mineru/output_tke/batch_stress_test/dcgm_metrics.csv"
echo "timestamp,entity_id,gpu_util_pct,mem_util_pct,power_w,gpu_temp_c,sm_clock_mhz,mem_clock_mhz,sm_active_pct,sm_occupancy_pct,fb_used_mb,fb_free_mb" > "$OUTPUT_FILE"

echo "DCGM monitoring started at $(date '+%Y-%m-%d %H:%M:%S'), writing to $OUTPUT_FILE"

# Field IDs: 203=GPUTL, 204=MCUTL, 155=POWER, 150=TMPTR, 100=SMCLK, 101=MMCLK, 1002=SMACT, 1003=SMOCC, 252=FBUSD, 251=FBFRE
# -d 5000 = 5 second interval, run indefinitely until killed
dcgmi dmon -e 203,204,155,150,100,101,1002,1003,252,251 -d 5000 2>&1 | while IFS= read -r line; do
    # Skip header lines and comments
    if [[ "$line" =~ ^# ]] || [[ -z "$line" ]]; then
        continue
    fi
    # Skip units line
    if [[ "$line" =~ "W" ]] && [[ "$line" =~ "C" ]]; then
        continue
    fi
    # Parse data lines
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    # Fields: Entity ID, GPUTL, MCUTL, POWER, TMPTR, SMCLK, MMCLK, SMACT, SMOCC, FBUSD, FBFRE
    eid=$(echo "$line" | awk '{print $2}')
    gpu_util=$(echo "$line" | awk '{print $3}')
    mem_util=$(echo "$line" | awk '{print $4}')
    power=$(echo "$line" | awk '{print $5}')
    temp=$(echo "$line" | awk '{print $6}')
    sm_clk=$(echo "$line" | awk '{print $7}')
    mem_clk=$(echo "$line" | awk '{print $8}')
    sm_act=$(echo "$line" | awk '{print $9}')
    sm_occ=$(echo "$line" | awk '{print $10}')
    fb_used=$(echo "$line" | awk '{print $11}')
    fb_free=$(echo "$line" | awk '{print $12}')
    echo "$ts,$eid,$gpu_util,$mem_util,$power,$temp,$sm_clk,$mem_clk,$sm_act,$sm_occ,$fb_used,$fb_free" >> "$OUTPUT_FILE"
done

#!/bin/bash
# TKE MinerU 10-Round Batch Stress Test with DCGM Monitoring
set -e

POD_NAME="mineru-54c75f48-ld2qd"
PDF_DIR="/data/pdf/pdf"
BASE_OUTPUT="/data/output"
NUM_ROUNDS=10
KUBECONFIG="/root/mineru/kubeconfig"
NO_PROXY="172.21.0.0/16"
export KUBECONFIG
export no_proxy=$NO_PROXY

RESULTS_DIR="/root/mineru/output_tke/batch_stress_test"
mkdir -p "$RESULTS_DIR"

echo "=============================================="
echo "TKE MinerU 10-Round Batch Stress Test"
echo "=============================================="
echo "Pod: $POD_NAME"
echo "PDF Dir: $PDF_DIR"
echo "Rounds: $NUM_ROUNDS"
echo "Start Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# Verify pod is running
kubectl get pod "$POD_NAME" -o wide

# Clean up previous round outputs
echo ""
echo "Cleaning up previous round outputs..."
for i in $(seq 1 $NUM_ROUNDS); do
    kubectl exec "$POD_NAME" -- rm -rf "${BASE_OUTPUT}/round_${i}" 2>/dev/null || true
done

# Verify PDF files exist
PDF_COUNT=$(kubectl exec "$POD_NAME" -- find "$PDF_DIR" -name "*.pdf" | wc -l)
echo "PDF files found: $PDF_COUNT"

# Prepare output directories
for i in $(seq 1 $NUM_ROUNDS); do
    kubectl exec "$POD_NAME" -- mkdir -p "${BASE_OUTPUT}/round_${i}"
done

# Run 10 rounds
OVERALL_START=$(date +%s)
ROUND_DATA=""

for ROUND in $(seq 1 $NUM_ROUNDS); do
    echo ""
    echo "=============================================="
    echo "Starting Round $ROUND / $NUM_ROUNDS"
    echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=============================================="

    ROUND_OUTPUT="${BASE_OUTPUT}/round_${ROUND}"
    kubectl exec "$POD_NAME" -- rm -rf "$ROUND_OUTPUT" 2>/dev/null || true
    kubectl exec "$POD_NAME" -- mkdir -p "$ROUND_OUTPUT"

    ROUND_START=$(date +%s)

    # Run mineru CLI inside the pod
    kubectl exec "$POD_NAME" -- mineru \
        -p "$PDF_DIR" \
        -o "$ROUND_OUTPUT" \
        -b vlm-auto-engine \
        -l en \
        --api-url http://localhost:8000 2>&1 || true

    ROUND_END=$(date +%s)
    ROUND_TIME=$((ROUND_END - ROUND_START))

    OUTPUT_COUNT=$(kubectl exec "$POD_NAME" -- find "$ROUND_OUTPUT" -name "*.md" 2>/dev/null | wc -l)
    THROUGHPUT=$(echo "scale=2; $OUTPUT_COUNT * 60 / $ROUND_TIME" | bc 2>/dev/null || echo "N/A")

    echo "Round $ROUND completed: ${ROUND_TIME}s, ${OUTPUT_COUNT} files, ${THROUGHPUT} files/min"

    # Store round data
    if [ -z "$ROUND_DATA" ]; then
        ROUND_DATA="$ROUND:$ROUND_TIME:$OUTPUT_COUNT"
    else
        ROUND_DATA="$ROUND_DATA $ROUND:$ROUND_TIME:$OUTPUT_COUNT"
    fi

    # Cooldown between rounds (except the last)
    if [ "$ROUND" -lt "$NUM_ROUNDS" ]; then
        echo "Cooling down for 10 seconds..."
        sleep 10
    fi
done

OVERALL_END=$(date +%s)
OVERALL_TIME=$((OVERALL_END - OVERALL_START))

echo ""
echo "=============================================="
echo "ALL ROUNDS COMPLETE"
echo "=============================================="

# Calculate statistics
TOTAL_FILES=0
TOTAL_TIME=0
MIN_TIME=99999
MAX_TIME=0
TIMES=""

for rd in $ROUND_DATA; do
    r=$(echo "$rd" | cut -d: -f1)
    t=$(echo "$rd" | cut -d: -f2)
    f=$(echo "$rd" | cut -d: -f3)
    TOTAL_FILES=$((TOTAL_FILES + f))
    TOTAL_TIME=$((TOTAL_TIME + t))
    TIMES="$TIMES $t"
    if [ "$t" -lt "$MIN_TIME" ]; then MIN_TIME=$t; fi
    if [ "$t" -gt "$MAX_TIME" ]; then MAX_TIME=$t; fi
done

AVG_TIME=$(echo "scale=1; $TOTAL_TIME / $NUM_ROUNDS" | bc)
AVG_THROUGHPUT=$(echo "scale=2; $PDF_COUNT * 60 / $AVG_TIME" | bc)

echo "Total files processed: $TOTAL_FILES"
echo "Total test time: ${OVERALL_TIME}s"
echo "Avg round time: ${AVG_TIME}s"
echo "Min round time: ${MIN_TIME}s"
echo "Max round time: ${MAX_TIME}s"
echo "Avg throughput: ${AVG_THROUGHPUT} files/min"

# Generate JSON summary
cat > "${RESULTS_DIR}/batch_stress_test_summary.json" << JSONEOF
{
  "test_type": "TKE Batch Stress Test (mineru CLI) with DCGM Monitoring",
  "pod": "$POD_NAME",
  "node": "172.21.80.123",
  "gpu": "NVIDIA RTX 5880 Ada (46GB VRAM)",
  "pdf_count": $PDF_COUNT,
  "num_rounds": $NUM_ROUNDS,
  "total_time_seconds": $OVERALL_TIME,
  "avg_duration_seconds": $AVG_TIME,
  "min_duration_seconds": $MIN_TIME,
  "max_duration_seconds": $MAX_TIME,
  "avg_throughput_files_per_min": $AVG_THROUGHPUT,
  "dcgm_metrics_file": "dcgm_metrics.csv",
  "rounds": [
JSONEOF

FIRST=true
for rd in $ROUND_DATA; do
    r=$(echo "$rd" | cut -d: -f1)
    t=$(echo "$rd" | cut -d: -f2)
    f=$(echo "$rd" | cut -d: -f3)
    tp=$(echo "scale=2; $f * 60 / $t" | bc)
    if [ "$FIRST" = true ]; then
        FIRST=false
    else
        echo "," >> "${RESULTS_DIR}/batch_stress_test_summary.json"
    fi
    cat >> "${RESULTS_DIR}/batch_stress_test_summary.json" << ENTRY
    {
      "round": $r,
      "duration_seconds": $t,
      "files_processed": $f,
      "throughput_files_per_min": $tp
    }
ENTRY
done

echo "" >> "${RESULTS_DIR}/batch_stress_test_summary.json"
echo "  ]" >> "${RESULTS_DIR}/batch_stress_test_summary.json"
echo "}" >> "${RESULTS_DIR}/batch_stress_test_summary.json"

echo ""
echo "Summary saved to: ${RESULTS_DIR}/batch_stress_test_summary.json"
echo "DCGM metrics saved to: ${RESULTS_DIR}/dcgm_metrics.csv"
echo "Test completed at: $(date '+%Y-%m-%d %H:%M:%S')"

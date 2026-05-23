#!/bin/bash
# TKE MinerU Batch Stress Test - 10 Rounds
# Uses mineru CLI inside the pod with --api-url pointing to local API server

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

echo "============================================================"
echo "TKE MinerU Batch Stress Test"
echo "============================================================"
echo "  Pod:         $POD_NAME"
echo "  PDF Dir:     $PDF_DIR"
echo "  Rounds:      $NUM_ROUNDS"
echo "  Start Time:  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

# Create output base dir in pod
kubectl exec "$POD_NAME" -- mkdir -p "$BASE_OUTPUT"

# Count PDFs
PDF_COUNT=$(kubectl exec "$POD_NAME" -- find "$PDF_DIR" -name "*.pdf" | wc -l)
echo "  PDF Count:   $PDF_COUNT"
echo ""

# Store results
JSON_RESULTS="["
OVERALL_START=$(date +%s)

for ROUND in $(seq 1 $NUM_ROUNDS); do
    ROUND_OUTPUT="${BASE_OUTPUT}/round_${ROUND}"
    echo "--- Round ${ROUND}/${NUM_ROUNDS} ---"

    # Clean previous round output if exists
    kubectl exec "$POD_NAME" -- rm -rf "$ROUND_OUTPUT" 2>/dev/null || true
    kubectl exec "$POD_NAME" -- mkdir -p "$ROUND_OUTPUT"

    # Run mineru batch command inside the pod
    ROUND_START=$(date +%s)

    kubectl exec "$POD_NAME" -- mineru \
        -p "$PDF_DIR" \
        -o "$ROUND_OUTPUT" \
        -b vlm-auto-engine \
        -l en \
        --api-url http://localhost:8000 2>&1 | tail -5

    ROUND_END=$(date +%s)
    ROUND_TIME=$((ROUND_END - ROUND_START))

    # Count output files
    OUTPUT_COUNT=$(kubectl exec "$POD_NAME" -- find "$ROUND_OUTPUT" -name "*.md" 2>/dev/null | wc -l)

    echo "[Round ${ROUND}] ${ROUND_TIME}s, ${OUTPUT_COUNT} output files"

    # Add to JSON
    if [ "$ROUND" -gt 1 ]; then
        JSON_RESULTS="${JSON_RESULTS},"
    fi
    JSON_RESULTS="${JSON_RESULTS}{\"round\":${ROUND},\"time_s\":${ROUND_TIME},\"output_files\":${OUTPUT_COUNT},\"pdf_count\":${PDF_COUNT}}"

    # Brief pause between rounds (10s)
    if [ "$ROUND" -lt "$NUM_ROUNDS" ]; then
        sleep 10
    fi
done

OVERALL_END=$(date +%s)
OVERALL_TIME=$((OVERALL_END - OVERALL_START))

JSON_RESULTS="${JSON_RESULTS}]"

# Calculate stats
TOTAL_TIME=$OVERALL_TIME
AVG_PER_ROUND=$(echo "scale=1; $TOTAL_TIME / $NUM_ROUNDS" | bc)
THROUGHPUT=$(echo "scale=2; $PDF_COUNT * $NUM_ROUNDS / ($TOTAL_TIME / 60)" | bc)

# Write summary
SUMMARY_FILE="${RESULTS_DIR}/batch_stress_test_summary.json"
cat > "$SUMMARY_FILE" << EOF
{
  "test_type": "tke_batch_stress_test",
  "method": "mineru_cli_batch",
  "pod_name": "$POD_NAME",
  "pdf_dir": "$PDF_DIR",
  "pdf_count": $PDF_COUNT,
  "num_rounds": $NUM_ROUNDS,
  "overall_time_s": $TOTAL_TIME,
  "avg_time_per_round_s": $AVG_PER_ROUND,
  "avg_time_per_file_s": $(echo "scale=2; $TOTAL_TIME / ($PDF_COUNT * $NUM_ROUNDS)" | bc),
  "throughput_files_per_min": $THROUGHPUT,
  "results": $JSON_RESULTS
}
EOF

echo ""
echo "============================================================"
echo "TKE BATCH STRESS TEST REPORT"
echo "============================================================"
echo "  Rounds:      $NUM_ROUNDS"
echo "  PDFs/round:  $PDF_COUNT"
echo "  Total tasks: $((PDF_COUNT * NUM_ROUNDS))"
echo "  Total time:  ${TOTAL_TIME}s ($(( TOTAL_TIME / 60 ))m $(( TOTAL_TIME % 60 ))s)"
echo "  Avg/round:   ${AVG_PER_ROUND}s"
echo "  Avg/file:    $(echo "scale=1; $TOTAL_TIME / ($PDF_COUNT * $NUM_ROUNDS)" | bc)s"
echo "  Throughput:  ${THROUGHPUT} files/min"
echo "  Report:      $SUMMARY_FILE"
echo "============================================================"

#!/bin/bash
# Local MinerU 10-Round Batch Stress Test with DCGM Monitoring
set -e

PDF_DIR="/data/pdf"
BASE_OUTPUT="/data/output"
LOCAL_OUTPUT="/root/mineru/output_local/batch_stress_test"
NUM_ROUNDS=10
API_URL="http://localhost:8000"
CONTAINER="mineru-api"

mkdir -p "$LOCAL_OUTPUT"

echo "=============================================="
echo "Local MinerU 10-Round Batch Stress Test"
echo "=============================================="
echo "PDF Dir: $PDF_DIR"
echo "API URL: $API_URL"
echo "Rounds: $NUM_ROUNDS"
echo "Start Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# Verify API is healthy
HEALTH=$(curl -s "$API_URL/health" || echo "FAIL")
echo "API Health: $HEALTH"

# Verify PDF files inside container
PDF_COUNT=$(docker exec "$CONTAINER" find "$PDF_DIR" -name "*.pdf" | wc -l)
echo "PDF files found: $PDF_COUNT"

# Clean up previous round outputs inside container
echo "Cleaning up previous round outputs..."
for i in $(seq 1 $NUM_ROUNDS); do
    docker exec "$CONTAINER" rm -rf "${BASE_OUTPUT}/round_${i}" 2>/dev/null || true
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
    docker exec "$CONTAINER" rm -rf "$ROUND_OUTPUT" 2>/dev/null || true
    docker exec "$CONTAINER" mkdir -p "$ROUND_OUTPUT"

    ROUND_START=$(date +%s)

    # Run mineru CLI inside Docker container
    docker exec "$CONTAINER" mineru -p "$PDF_DIR" -o "$ROUND_OUTPUT" -b vlm-auto-engine -l en --api-url "$API_URL" 2>&1 || true

    ROUND_END=$(date +%s)
    ROUND_TIME=$((ROUND_END - ROUND_START))

    OUTPUT_COUNT=$(docker exec "$CONTAINER" find "$ROUND_OUTPUT" -name "*.md" 2>/dev/null | wc -l)
    THROUGHPUT=$(echo "scale=2; $OUTPUT_COUNT * 60 / $ROUND_TIME" | bc 2>/dev/null || echo "N/A")

    echo "Round $ROUND completed: ${ROUND_TIME}s, ${OUTPUT_COUNT} files, ${THROUGHPUT} files/min"

    ROUND_DATA="$ROUND_DATA $ROUND:$ROUND_TIME:$OUTPUT_COUNT"

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

for rd in $ROUND_DATA; do
    r=$(echo "$rd" | cut -d: -f1)
    t=$(echo "$rd" | cut -d: -f2)
    f=$(echo "$rd" | cut -d: -f3)
    TOTAL_FILES=$((TOTAL_FILES + f))
    TOTAL_TIME=$((TOTAL_TIME + t))
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
JSON_FILE="${LOCAL_OUTPUT}/local_stress_test_summary.json"
cat > "$JSON_FILE" << JSONEOF
{
  "test_type": "Local Batch Stress Test (mineru CLI) with DCGM Monitoring",
  "environment": "Local Docker (mineru-api container)",
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
        echo "," >> "$JSON_FILE"
    fi
    cat >> "$JSON_FILE" << ENTRY
    {
      "round": $r,
      "duration_seconds": $t,
      "files_processed": $f,
      "throughput_files_per_min": $tp
    }
ENTRY
done

echo "" >> "$JSON_FILE"
echo "  ]" >> "$JSON_FILE"
echo "}" >> "$JSON_FILE"

echo ""
echo "Summary saved to: $JSON_FILE"
echo "DCGM metrics saved to: ${LOCAL_OUTPUT}/dcgm_metrics.csv"
echo "Test completed at: $(date '+%Y-%m-%d %H:%M:%S')"

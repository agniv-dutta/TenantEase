#!/usr/bin/env sh
# Seed, train and serve with no API key needed. Trained artifacts are reused on
# restart so the container comes up quickly the second time.
set -e

mkdir -p /data

if [ ! -f /data/khata.db ]; then
  echo "Seeding synthetic database..."
  python -m app.ml.synth --seed "${SEED:-42}" --out /data/khata.db
fi

if [ ! -f app/ml/artifacts/model.joblib ]; then
  echo "Training model..."
  python -m app.ml.train
  python -m app.ml.evaluate
  python -m app.ml.simulate
  python -m app.llm.eval
fi

echo "Scoring the open cycle..."
python -m app.ml.scoring || true

echo "Starting API on :8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

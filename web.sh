#!/bin/bash
cd "$(dirname "$0")"
# 'python -m streamlit' e não '.venv/bin/streamlit': o atalho do venv guarda o
# caminho absoluto de quando foi criado e quebrou quando a pasta mudou de lugar.
.venv/bin/python -m streamlit run app.py "$@"

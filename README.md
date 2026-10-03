# LiquidityAI

LiquidityAI is a Python research and automation tool for crypto liquidity and heatmap analysis. It includes screen capture, OCR, Coinglass automation helpers, liquidity analysis, prediction modules, threshold learning, trade tracking, and overlay/UI components.

The main application source lives under the nested `LiquidityAI` directory.

## Features

- Liquidity heatmap capture and analysis
- OCR and screen capture pipeline
- Coinglass automation helpers
- Prediction and online model modules
- Threshold learning and feature extraction
- Trade tracking and log analysis
- Overlay and macro-builder UI modules
- Configurable trading pairs and macros

## Tech Stack

- Python
- OCR/screen capture utilities
- Image processing modules
- Local JSON configuration
- Batch launcher scripts

## Project Layout

```text
LiquidityAI/
├── main.py
├── ui_main.py
├── ui_macro_builder.py
├── modules/
│   ├── liquidity_analyzer.py
│   ├── prediction_engine.py
│   ├── screen_capture.py
│   ├── ocr_reader.py
│   └── coinglass_automator.py
├── config.json
├── pairs.json
└── requirements.txt
```

## Setup

```powershell
cd LiquidityAI
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Notes

This is an experimental market-analysis and automation project. Validate all outputs manually before using them for trading decisions.


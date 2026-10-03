# LiquidityAI

LiquidityAI is a Python project for studying crypto liquidity and heatmaps.

In simple words, this app is made to capture market-related screen data, read parts of the screen with OCR, analyze liquidity areas, and help track possible trading ideas. It also includes automation helpers and UI files.

The main application code is inside the nested `LiquidityAI` folder.

## What This App Can Do

- Capture screen information.
- Read text from the screen using OCR.
- Analyze liquidity heatmaps.
- Work with Coinglass-style automation helpers.
- Track trades and logs.
- Use prediction and learning modules for research.
- Configure trading pairs and macros.
- Show overlay and macro-builder UI modules.

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

## Safety Notes

This is an experimental research project. It should not be trusted blindly for trading.

Always check the output manually before making any trading decision. This project is not financial advice.

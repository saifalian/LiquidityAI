# Crypto Liquidity AI Prediction System

A real-time ML system that reads Coinglass liquidity heatmaps, auto-interacts with the UI, learns long/short liquidity zones, and predicts short-term crypto price movement.

## Prerequisites

1.  **Python 3.10+**: You must have Python installed. If not, download it from [python.org](https://www.python.org/downloads/) and ensure it is added to your system PATH.
2.  **Tesseract OCR**: You must install Tesseract OCR separately.
    *   Windows: Download the installer from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and install it.
    *   Ensure the installation path (typically `C:\Program Files\Tesseract-OCR\tesseract.exe`) is known, as it will be needed by the OCR module.

## Installation

1.  Open a terminal or command prompt in this directory.
2.  Install the required Python packages:

```bash
pip install -r requirements.txt
```

## Setup & Usage

1.  **Calibration Phase**: Run `python calibrate.py` to define the screen coordinates for the Coinglass heatmap, price axis, threshold slider, and pair search button. This builds `config.json`.
2.  **Desktop UI (Recommended)**: Run `python ui_main.py` to launch the full PyQt5 desktop dashboard. From here, you can automate adding pairs, start background prediction threads, view live logs and prediction tables with Take Profit/Stop Loss statistics, and record your screen.
3.  **CLI Observation Phase**: Run `python main.py --mode observe --pair XRPUSDT --duration 15` to let the system watch the heatmap for 15 minutes and build an initial feature baseline.
4.  **CLI Prediction Phase**: Run `python main.py --mode predict --pair XRPUSDT`. A transparent overlay can be launched via `python modules/overlay.py` to display live predictions.

## Disclaimer

This system is for educational and research purposes. Crypto trading involves significant financial risk. Always do your own due diligence.

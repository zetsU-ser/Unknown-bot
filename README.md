# 🦇 Unknown-bot: Zetsu Hunt Edition (V9.1)

Motor de Trading Algorítmico Cuantitativo de Alta Frecuencia (HFT) diseñado para el par BTC/USDT. Construido con una arquitectura modular basada en Smart Money Concepts (SMC), Análisis de Volumen Institucional y Gestión de Riesgo Dinámica.

## 🧠 Arquitectura de 6 Bloques

1. **Estructura de Mercado (Bloque 1):** Detección de regímenes, niveles Premium/Discount (Fibonacci 0.5) y estructura de Dow.
2. **Liquidez (Bloque 2):** Detección de Order Blocks (OB) y Liquidity Sweeps para cazar Stops de retail.
3. **Volumen Institucional (Bloque 3):** Integración de VWAP y Divergencias de Cumulative Volume Delta (CVD) para evitar trampas (Bull/Bear Traps).
4. **Motor Bayesiano (Bloque 4):** Sistema de inferencia probabilística que evalúa la confluencia de variables para clasificar setups (Scout, Ambush, Unicorn).
5. **Gestión de Riesgo Dinámica (Bloque 5):** Posicionamiento basado en el Criterio de Kelly Fraccional (Fractional Kelly) con adaptación al Drawdown (Asimetría de la Ruina).
6. **Infraestructura Quant (Bloque 6):** Procesamiento vectorial en memoria con `Polars` y almacenamiento particionado en `PostgreSQL`.

## 📂 Estructura del Proyecto
* `analysis/` : Indicadores técnicos, Estructura SMC y Perfil de Volumen (CVD/VWAP)
* `configs/` : Hiperparámetros, pesos del motor y variables de entorno
* `core/` : Decision Engine (Oráculo Bayesiano) y Risk Manager (Kelly/Triple Barrier)
* `data/` : Ingesta y descarga de datos históricos
* `execution/` : Entorno de paper trading y simulación de wallet
* `infra/` : Configuración de base de datos y Docker
* `research/` : Backtester V9.1 y Laboratorio Forense para optimización estadística

## 🚀 Rendimiento Histórico (Backtest V9.1)
* **Capital Inicial:** $10,000.00
* **Capital Final:** $11,401.93 (+14.01%)
* **Win Rate:** 44.93%
* **R:R Realizado:** 1.90
* **Asimetría Neta:** +0.257% (Edge Matemático Positivo)
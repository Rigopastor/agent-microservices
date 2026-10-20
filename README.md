# Agent Microservices

Servicios baratos y fiables para agentes AI.

## Servicios
- POST /uptime → 0.004 USDC
- POST /ssl → 0.005 USDC
- POST /metadata → 0.008 USDC

## Desarrollo local
```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
# Channel-Gateway SERVICE

## SET UP ENV

### Create conda env

```bash
conda create -n channel-gateway-env python=3.13 uv -c conda-forge
```

### Activate conda env

```bash
conda activate channel-gateway-env
```

### Install dependancies

```bash
cd src
uv pip install -r requirements.txt
```

## START APP

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

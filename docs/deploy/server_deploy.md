# Server Deployment (Conda)

This guide deploys the Streamlit app on port `51062` and the gRPC service on port
`18000` on a Linux server using an existing conda installation.

## 1. Prepare the Environment

```bash
cd /opt
git clone <your-repo-url> somni-graph-quiz
cd somni-graph-quiz

# Use an existing env or create one.
conda create -n somni-graph-quiz python=3.11 -y
conda run -n somni-graph-quiz python -m pip install -e .
```

## 2. Configure `.env`

Create `.env` in the project root:

```env
SOMNI_LLM_BASE_URL=...
SOMNI_LLM_API_KEY=...
SOMNI_LLM_MODEL=...
SOMNI_LLM_TEMPERATURE=0.2
SOMNI_LLM_TIMEOUT=30
SOMNI_LLM_REASONING_EFFORT=minimal
SOMNI_GRPC_HOST=0.0.0.0
SOMNI_GRPC_PORT=18000
```

## 3. Run Services (Foreground)

```bash
conda run -n somni-graph-quiz streamlit run app.py \
  --server.address 0.0.0.0 \
  --server.port 51062 \
  --server.headless true

conda run -n somni-graph-quiz python -m somni_graph_quiz.adapters.grpc
```

Streamlit: `http://<server-ip>:51062/`
gRPC: `http://<server-ip>:18000/`

## 4. Optional: systemd Units

Find the conda executable path (example: `/opt/conda/bin/conda`) and update
the `ExecStart` lines below if `/usr/bin/conda` is not correct.

Create `/etc/systemd/system/somni-graph-quiz-streamlit.service`:

```ini
[Unit]
Description=Somni Graph Quiz Streamlit
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/somni-graph-quiz
EnvironmentFile=/opt/somni-graph-quiz/.env
ExecStart=/usr/bin/conda run -n somni-graph-quiz python -m streamlit run /opt/somni-graph-quiz/app.py --server.address 0.0.0.0 --server.port 51062 --server.headless true --browser.gatherUsageStats false
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/somni-graph-quiz-grpc.service`:

```ini
[Unit]
Description=Somni Graph Quiz gRPC
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/somni-graph-quiz
EnvironmentFile=/opt/somni-graph-quiz/.env
Environment=SOMNI_GRPC_PORT=18000
ExecStart=/usr/bin/conda run -n somni-graph-quiz python -m somni_graph_quiz.adapters.grpc
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```bash
systemctl daemon-reload
systemctl enable somni-graph-quiz-streamlit somni-graph-quiz-grpc
systemctl start somni-graph-quiz-streamlit somni-graph-quiz-grpc
```

Check status:

```bash
systemctl status somni-graph-quiz-streamlit
systemctl status somni-graph-quiz-grpc
```

## 5. Recommended Deployment Script

Use the repository script to keep the remote `.env`, editable install, and
systemd units aligned with `51062/18000`:

```bash
python scripts/deploy_server.py \
  --host 43.138.100.224 \
  --user root \
  --password 'your-password'
```

## 6. Firewall

Make sure ports `51062` and `18000` are open in the server firewall or security group.

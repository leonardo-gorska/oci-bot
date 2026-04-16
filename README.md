# 🤖 OCI A1.Flex Instance Creator Bot

Bot que roda na sua VM Oracle de 1GB e fica tentando criar automaticamente uma instância **ARM A1.Flex** (4 OCPUs, 24GB RAM) — o recurso Always Free que está sempre com "Out of host capacity" em São Paulo.

## 📋 O que faz

- Tenta criar a instância a cada **60 segundos** (configurável)
- Quando recebe "Out of host capacity", espera e tenta de novo
- Quando **conseguir**, para automaticamente e te **avisa no Telegram** (opcional)
- Roda como **serviço do sistema** (`systemd`) — sobrevive a reboots
- **Super leve** — usa menos de 50MB de RAM

---

## 🚀 Guia Rápido

### 1. Gerar API Key no OCI Console

1. Acesse [cloud.oracle.com](https://cloud.oracle.com)
2. Clique no ícone do seu perfil → **My Profile**
3. Vá em **API Keys** → **Add API Key**
4. Escolha **Generate API Key Pair**
5. Baixe a **Private Key** (arquivo `.pem`)
6. Clique em **Add**
7. Copie os valores que aparecem (tenancy OCID, user OCID, fingerprint)

### 2. Coletar os IDs necessários

| Dado | Onde encontrar no OCI Console |
|------|-------------------------------|
| `tenancy_ocid` | Perfil → Tenancy → Copiar OCID |
| `user_ocid` | Perfil → My Profile → Copiar OCID |
| `fingerprint` | Perfil → API Keys → Fingerprint da chave |
| `compartment_id` | Identity → Compartments → OCID do root |
| `subnet_id` | Networking → Virtual Cloud Networks → sua VCN → Subnet → OCID |
| `image_id` | Compute → Images → Escolha Oracle Linux 8 ou Ubuntu → OCID |
| `availability_domain` | Identity → Availability Domains → Nome completo |

> **💡 Dica:** O `compartment_id` geralmente é igual ao `tenancy_ocid` se você não criou compartments extras.

### 3. Fazer upload do bot para a VM

```bash
# Na sua máquina local, envia os arquivos para a VM de 1GB
scp -r oci-bot/ opc@SEU_IP_DA_VM:~/oci-bot/
```

### 4. Instalar na VM

```bash
# Conecta na VM
ssh opc@SEU_IP_DA_VM

# Entra na pasta
cd ~/oci-bot

# Copia e preenche a config
cp config.example.json config.json
nano config.json   # Preencha todos os campos

# Copia a chave .pem para a VM
# (suba o arquivo .pem via scp e coloque em ~/.oci/)
mkdir -p ~/.oci
# scp da máquina local: scp oci_api_key.pem opc@IP:~/.oci/

# Roda o setup
chmod +x setup.sh
./setup.sh
```

### 5. Testar manualmente

```bash
# Testa antes de colocar em background
./venv/bin/python3 oci_instance_bot.py
```

Se as credenciais estiverem certas, você verá:
```
✅ Autenticação OK!
🚀 Iniciando tentativas de criação da instância...
📡 Tentativa #1 (rodando há 0h00m00s)...
   ❌ Sem capacidade (InternalError: 500). Aguardando 60s...
```

### 6. Rodar em background (serviço)

```bash
sudo systemctl start oci-bot
sudo systemctl status oci-bot  # Verifica se está rodando

# Logs em tempo real
sudo journalctl -u oci-bot -f
```

---

## 📱 Telegram (opcional)

Para receber notificação quando a instância for criada:

1. **Crie um bot**: Fale com [@BotFather](https://t.me/BotFather) no Telegram → `/newbot`
2. **Pegue o token**: O BotFather te dá o token do bot
3. **Pegue seu chat_id**: Fale com [@userinfobot](https://t.me/userinfobot) no Telegram
4. **Configure no `config.json`**:
   ```json
   "telegram": {
       "bot_token": "123456:ABC-DEF...",
       "chat_id": "987654321"
   }
   ```

---

## ⚙️ Configurações

No `config.json`:

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `retry_interval_seconds` | `60` | Segundos entre cada tentativa |
| `max_attempts` | `0` | Máximo de tentativas (0 = infinito) |
| `ocpus` | `4` | Número de OCPUs (máx. 4 no Always Free) |
| `memory_gb` | `24` | RAM em GB (máx. 24 no Always Free) |
| `boot_volume_size_gb` | `50` | Tamanho do disco de boot em GB |

---

## 📌 Comandos Úteis

```bash
# Status do serviço
sudo systemctl status oci-bot

# Parar o bot
sudo systemctl stop oci-bot

# Reiniciar
sudo systemctl restart oci-bot

# Ver logs
sudo journalctl -u oci-bot -f
tail -f ~/oci-bot/oci_bot.log

# Desinstalar o serviço
sudo systemctl stop oci-bot
sudo systemctl disable oci-bot
sudo rm /etc/systemd/system/oci-bot.service
sudo systemctl daemon-reload
```

---

## 💡 Dica Importante

> **Converta sua conta para Pay-As-You-Go (PAYG)!**
> Mesmo usando apenas recursos Always Free, contas PAYG têm **prioridade** na alocação de recursos.
> A chance de conseguir a máquina ARM sobe **muito**.
> Configure um alerta de orçamento ($1) para garantir que não será cobrado.

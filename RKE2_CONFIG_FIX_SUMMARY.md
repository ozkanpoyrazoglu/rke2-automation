# RKE2 Config Fix

## Sorun

Eski `config.yaml.j2` `rke2_type` kullanıyordu:
```yaml
{% if rke2_type != "server" %}
server: https://{{ rke2_api_ip }}:9345
{% endif %}
```

**Problem:**
- Tüm master'lar (initial + joining) `rke2_type: server` idi
- Bu yüzden hiçbir master `server:` parametresi almıyordu
- Joining master'larda `server:` olması ZORUNLU
- Sadece initial master'da `server:` olmamalı

## Çözüm

Role-based config ile düzeltildi. Database'deki `NodeRole` kullanılıyor:

### Backend Değişiklikleri

**ansible_generator.py:**
- Her node için `host_vars/<hostname>.yaml` oluşturuluyor
- `config_template` node role'e göre belirleniyor:
  - `INITIAL_MASTER` → `config_initial_master.yaml.j2` (server YOK)
  - `MASTER` → `config_joining_master.yaml.j2` (server VAR)
  - `WORKER` → `config_worker.yaml.j2` (server VAR)

**ansible_service.py:**
- `execute_add_nodes()` yeni node'lar için host_vars oluşturuyor
- Role belirleme:
  - Mevcut master varsa: yeni server → `MASTER` (joining)
  - Mevcut master yoksa: ilk server → `INITIAL_MASTER`
  - Tüm agent'lar → `WORKER`

### Playbook Değişiklikleri

- `install_rke2.yml` ve `add_node.yml`: `{{ config_template }}` kullanıyor

## Örnek Config'ler

### HA Cluster (3 Master + 1 Worker)

**Initial Master (m1) - server parametresi YOK:**
```yaml
token: F9HWlc--H8NXSJadfasdfadfafedoQBxWJM
tls-san:
  - 10.0.1.10
  - 10.0.1.11
cni: canal
```

**Joining Master (m2, m3) - server parametresi VAR:**
```yaml
server: https://10.0.1.10:9345
token: F9HWlc--H8NXSJadfasdfadfafedoQBxWJM
tls-san:
  - 10.0.1.10
  - 10.0.1.11
cni: canal
```

**Worker (w1) - server parametresi VAR:**
```yaml
server: https://10.0.1.10:9345
token: F9HWlc--H8NXSJadfasdfadfafedoQBxWJM
```

## Değiştirilen Dosyalar

- `backend/app/services/ansible_generator.py` - host_vars generation
- `backend/app/services/ansible_service.py` - add node logic
- `ansible/playbooks/install_rke2.yml` - template variable
- `ansible/playbooks/add_node.yml` - template variable

**Template'ler:**
- `config_initial_master.yaml.j2` - server parametresi yok
- `config_joining_master.yaml.j2` - server parametresi var
- `config_worker.yaml.j2` - server parametresi var

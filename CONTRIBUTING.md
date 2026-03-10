# Contribuir a TETRA Monitor

## Ramas

| Rama | Propósito |
|---|---|
| `develop` | Rama de trabajo diario — todos los commits van aquí |
| `master` | Producción — solo recibe merges desde `develop` vía PR |

**Nunca hagas commits directos a `master`.** El CI bloquea el merge si los tests no pasan.

---

## Flujo de trabajo

```bash
# 1. Parte siempre desde develop actualizado
git checkout develop
git pull origin develop

# 2. Crea una rama de feature (opcional para cambios pequeños)
git checkout -b feat/nombre-descriptivo

# 3. Desarrolla y commitea
git add .
git commit -m "feat: descripción del cambio"

# 4. Push y abre PR a develop (o directamente a develop si es tu repo)
git push origin feat/nombre-descriptivo

# 5. Cuando develop está estable, abre PR develop → master
```

---

## Commits

Usamos [Conventional Commits](https://www.conventionalcommits.org/):

| Prefijo | Cuándo usarlo |
|---|---|
| `feat:` | Nueva funcionalidad |
| `fix:` | Corrección de bug |
| `fix(test):` | Corrección de un test |
| `refactor:` | Cambio de código sin cambiar comportamiento |
| `chore:` | Tareas de mantenimiento (deps, config, CI) |
| `docs:` | Cambios solo en documentación |
| `ci:` | Cambios en el workflow de CI |
| `test:` | Añadir o modificar tests |

---

## Entorno de desarrollo

```bash
# Clonar y entrar
git clone https://github.com/lluisasturies/tetra-monitor.git
cd tetra-monitor

# Entorno virtual
python3 -m venv venv
source venv/bin/activate

# Dependencias de producción + desarrollo
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## Tests

```bash
# Correr todos los tests
pytest tests/ -v

# Solo un fichero
pytest tests/test_pei_parser.py -v

# Con cobertura (requiere pytest-cov)
pytest tests/ --cov=src --cov-report=term-missing
```

Los tests no requieren hardware ni BD real — todo el hardware está mockeado.

---

## Lint

```bash
# Comprobar
ruff check src/ tests/

# Corregir automáticamente los fixables
ruff check src/ tests/ --fix
```

La configuración de `ruff` está en `pyproject.toml`.

---

## Versiones

Usamos [Semantic Versioning](https://semver.org/lang/es/). Al mergear a `master`:

1. Actualiza `[Unreleased]` en `CHANGELOG.md` con la versión y fecha
2. Actualiza `version` en `pyproject.toml`
3. Tras el merge, crea el tag:

```bash
git checkout master
git pull
git tag v1.2.0
git push origin v1.2.0
```

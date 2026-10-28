# Contributing to Knowledge Gateway

Thank you for your interest in contributing to **Knowledge Gateway**! We welcome community contributions, new connectors, cache backends, neural ranking improvements, bug fixes, and documentation improvements.

---

## 🛡️ Repository Protection & Contribution Model

To ensure code stability, security, and project integrity, **Knowledge Gateway operates under a strictly protected Fork & Pull Request model**:

1. **Direct Commits Prohibited**: Direct pushes to `main` are permanently blocked by branch protection rules.
2. **Upstream Branch Creation Restricted**: Contributors cannot create branches directly in `karthikrameshdev/knowledge-gateway`. All development branches must live in your own personal fork.
3. **Mandatory Code Review**: Every Pull Request requires automated CI checks to pass and explicit review and approval from `@karthikrameshdev` (enforced via [`CODEOWNERS`](.github/CODEOWNERS)).
4. **Squash Merging**: Pull requests are merged using squash commits to keep Git history clean, atomic, and readable.

---

## 🚀 Step-by-Step Contribution Workflow

### 1. Fork the Repository
Click the **Fork** button at the top-right corner of [https://github.com/karthikrameshdev/knowledge-gateway](https://github.com/karthikrameshdev/knowledge-gateway) to create a copy of the repository under your GitHub account.

### 2. Clone Your Fork
Clone your fork locally and configure the upstream remote:

```bash
# Clone your fork
git clone https://github.com/<your-username>/knowledge-gateway.git
cd knowledge-gateway

# Add upstream remote
git remote add upstream https://github.com/karthikrameshdev/knowledge-gateway.git
git fetch upstream
```

### 3. Create a Feature Branch on Your Fork
Always branch off the latest `upstream/main`:

```bash
git checkout main
git pull upstream main
git checkout -b feature/your-feature-name
# or for bug fixes:
git checkout -b fix/issue-description
```

### 4. Set Up the Local Development Environment
Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies and test suite
pip install --upgrade pip
pip install -r requirements.txt
```

Copy the example configuration and environment files:

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

*(Note: The test suite includes unit fixtures and offline fallback connectors, allowing tests to run 100% offline without live PostgreSQL or Docker dependencies).*

### 5. Make Your Changes and Run Tests
Ensure all code conforms to PEP 8 standards and passes the automated test suite before opening a PR:

```bash
# Run the complete test suite
pytest tests -v
```

### 6. Commit Your Changes
Write clear, conventional commit messages:

```bash
git add .
git commit -m "feat(connectors): add support for custom metadata filters"
```

Prefix commits appropriately:
- `feat:` New features or connectors
- `fix:` Bug fixes or cache invalidation repairs
- `docs:` Documentation updates
- `test:` Adding or updating tests
- `refactor:` Code improvements without behavioral changes

### 7. Push to Your Fork
Push your branch to your personal GitHub fork:

```bash
git push origin feature/your-feature-name
```

### 8. Open a Pull Request
1. Navigate to [https://github.com/karthikrameshdev/knowledge-gateway](https://github.com/karthikrameshdev/knowledge-gateway).
2. Click **Compare & pull request**.
3. Fill out the provided [Pull Request Template](.github/PULL_REQUEST_TEMPLATE.md) in full.
4. Link any related issues (e.g., `Fixes #25`).
5. Wait for the automated CI tests to complete and for review from the project maintainers.

---

## 📜 Code of Conduct

All contributors are expected to uphold the [Code of Conduct](CODE_OF_CONDUCT.md). Please treat all community members with respect, kindness, and professionalism.

## 🔒 Security Vulnerabilities

Please **do not** open public GitHub issues for security vulnerabilities. Instead, follow our responsible disclosure process in [SECURITY.md](SECURITY.md).

---
name: revisar
description: Revisa as mudanças atuais antes do commit usando o agente code-reviewer.
disable-model-invocation: true
---

1. Rode os testes (`cd backend && pytest`) e o lint (`ruff check .`).
2. Delegue ao agente `code-reviewer` a revisão das mudanças atuais (`git diff`).
3. Mostre o resultado em português e pergunte quais pontos devo corrigir.

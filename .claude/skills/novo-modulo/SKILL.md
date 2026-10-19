---
name: novo-modulo
description: Cria um módulo completo do Organizador (banco, API, testes) seguindo o padrão do projeto. Use quando eu pedir um módulo novo, como pets ou finanças.
argument-hint: [nome-do-modulo]
disable-model-invocation: true
---

Crie o módulo **$ARGUMENTS** de ponta a ponta, seguindo o CLAUDE.md.

1. **Plano primeiro.** Leia o CLAUDE.md, o ROADMAP e o módulo `tasks` (referência de padrão). Mostre tabelas, endpoints e regras de negócio propostos e ESPERE minha aprovação.
2. **Branch.** Crie `feat/$ARGUMENTS`.
3. **Banco.** Delegue ao agente `db-architect`: models e migration.
4. **API.** Delegue ao agente `backend-dev`: schemas, repository, service e router.
5. **Testes.** Delegue ao agente `test-writer`. Se ele relatar bugs, peça ao `backend-dev` para corrigir.
6. **Revisão.** Delegue ao agente `code-reviewer`. Corrija tudo que for 🔴.
7. **Fechamento.** Rode `pytest`, faça commits no padrão Conventional Commits e marque o item no `docs/ROADMAP.md`.

Termine com um resumo em português: o que foi criado, endpoints e como testar em `http://localhost:$API_PORT/api/docs`.

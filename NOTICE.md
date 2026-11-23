# BakeriQ — licensing notice

> **DRAFT — the author must confirm the list below before this notice is relied on.**
> VERIFY: the "reserved items" section was drafted from the files that exist in the repository, not from a decision recorded by the author. Add, remove or reword entries until it says exactly what you intend, then delete this banner. VERIFY also that the author owns the work being licensed: BakeriQ was built during an internship for a client bakery, so check ownership and any assignment of rights against the internship terms before publishing a licence over it.

BakeriQ is **partly open source and partly all rights reserved.**

## What is open source

The source code in this repository is released under the [MIT License](LICENSE), **except** for the items listed under "Reserved items" below. You may use, copy, modify, merge, publish, distribute and sell the MIT-licensed code, provided the copyright and licence notice are kept.

## Reserved items

The [LICENSE](LICENSE) file is the plain, unmodified MIT text so that tools and people recognise it. The "Software" it grants rights to does not include the items listed here.

The following are **not** covered by the MIT License. They remain **© 2026 San Shibu. All rights reserved.** You may read them as part of this public repository, but you may not copy, reuse, redistribute, modify or build on them without written permission from the author.

*Proposed entries (draft):*

1. **The "BakeriQ" name and brand** — the project name, the `favicon.svg` and `icons.svg` artwork under `frontend-customer/public/`, and any logo or wordmark used in the dashboard or customer app. The MIT grant covers the code, not the right to present a derived product under this name.
2. **The LLM order-parsing prompt and its supporting data** — the system prompt, the Malayalam/Manglish quantity-word table and the few-shot examples in `backend/app/services/llm_parser_service.py`.
3. **The WhatsApp message copy and template designs** — the wording of the bot's replies and the Twilio Content Template bodies and button labels in `backend/app/services/template_replies.py` and `backend/scripts/bootstrap_content_templates.py`.
4. **The seed data** — the sample customers, products and orders in `backend/scripts/seed_phase_2.py`.
5. **The written documentation** — `README.md` and the files under `docs/`, as text. (Linking to them and quoting short passages with attribution is fine.)

## Third-party software

BakeriQ depends on third-party packages (FastAPI, SQLAlchemy, React, Vite, Tailwind CSS and others) that are licensed by their own authors under their own terms. Nothing in this repository changes those terms.

## Contact

For permission to use a reserved item, contact the author through the GitHub profile [@scorpiocodex](https://github.com/scorpiocodex).

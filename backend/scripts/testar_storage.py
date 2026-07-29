"""
Smoke test do storage: grava, lê de volta, confere, apaga.

Uso (na OCI):
    venv/bin/python -m scripts.testar_storage

Prova que o STORAGE_LOCAL_DIR existe, é gravável, e o ciclo salvar→ler funciona
antes de a gente construir o upload de documento em cima.
"""

import os

from app.config import settings
from app import storage


def main() -> None:
    print(f"\nBackend: {settings.STORAGE_BACKEND}")
    print(f"Dir local: {settings.STORAGE_LOCAL_DIR}")

    if settings.STORAGE_BACKEND == "local":
        if not os.path.isdir(settings.STORAGE_LOCAL_DIR):
            print(f"\n✗ Diretório não existe. Crie com:")
            print(f"    mkdir -p {settings.STORAGE_LOCAL_DIR}")
            return
        if not os.access(settings.STORAGE_LOCAL_DIR, os.W_OK):
            print(f"\n✗ Sem permissão de escrita em {settings.STORAGE_LOCAL_DIR}")
            return

    conteudo = b"conteudo de teste do BSS - pode apagar"
    ref = storage.salvar(conteudo, "Certidão de Teste (2026).pdf")
    print(f"\n✓ Gravado. ref = {ref}")

    lido = storage.ler(ref)
    ok = (lido == conteudo)
    print(f"✓ Lido de volta: {'confere' if ok else '✗ DIFERENTE!'}")
    print(f"  existe()? {storage.existe(ref)}")

    # Limpa o arquivo de teste (só no local; em s3 deixaria pra lifecycle)
    if ref.startswith("local://"):
        os.remove(storage._caminho_local(ref))
        print("✓ Arquivo de teste removido.")

    print("\nStorage OK." if ok else "\n✗ Falhou.")


if __name__ == "__main__":
    main()

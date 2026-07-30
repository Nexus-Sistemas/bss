"""
Agendador de cadências — dispara os modelos de e-mail que "vencem hoje".

Uso (roda 1x/dia via systemd timer / cron):
    venv/bin/python -m scripts.disparar_cadencias
    venv/bin/python -m scripts.disparar_cadencias --dry-run   # só diz o que faria

REGRAS (cadência definida no editor de modelos):
  - manual       → nunca dispara aqui (só pelo botão)
  - diaria_util  → todo dia de semana (seg–sex)
  - dias_do_mes  → se hoje está na lista de dias; e, se postergar_fds estiver
                   ligado e um dia da lista caiu no fim de semana, dispara na
                   segunda seguinte (o "atrasado" do sábado/domingo).

IDEMPOTÊNCIA: modelo_disparo.disparar já pula quem recebeu hoje (log). Rodar o
job 2x no mesmo dia não duplica.

SEGURANÇA: respeita a trava EMAIL_REDIRECIONAR_PARA (em homolog, tudo vai pro
e-mail de teste). Ver modelo_disparo.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from app import modelo_disparo, modelo_repo


def _deve_disparar_hoje(modelo: dict, hoje: date) -> bool:
    tipo = modelo["cadencia_tipo"]
    dow = hoje.weekday()  # 0=segunda ... 5=sábado, 6=domingo

    if tipo == "diaria_util":
        return dow < 5   # seg–sex

    if tipo == "dias_do_mes":
        dias = set(modelo.get("cadencia_dias") or [])
        if not dias:
            return False
        if hoje.day in dias and dow < 5:
            return True   # o dia caiu num dia útil: dispara
        # Postergar: se hoje é segunda, cobre os dias da lista que caíram no
        # sábado (hoje-2) ou domingo (hoje-1) — o disparo "atrasado" do fds.
        if modelo.get("cadencia_postergar_fds") and dow == 0:
            sab, dom = hoje - timedelta(days=2), hoje - timedelta(days=1)
            return sab.day in dias or dom.day in dias
        return False

    return False   # manual


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    hoje = date.today()

    modelos = modelo_repo.listar_ativos_com_cadencia()
    print(f"[{hoje}] {len(modelos)} modelo(s) ativo(s) com cadência.")

    for m in modelos:
        if not _deve_disparar_hoje(m, hoje):
            continue
        print(f"  → {m['codigo']} ({m['cadencia_tipo']}): vence hoje.")
        if args.dry_run:
            r = modelo_disparo.preview(m)
            print(f"     [dry-run] {r['total']} receberiam"
                  f"{' (modo teste)' if r.get('redirecionado_para') else ''}.")
            continue
        r = modelo_disparo.disparar(m, origem="agendado")
        if r.get("erro"):
            print(f"     ✗ {r['erro']}")
        else:
            print(f"     ✓ {r['enviados']} enviado(s), "
                  f"{r['pulados_ja_enviado_hoje']} pulado(s), {r['falhas']} falha(s)"
                  f"{' (modo teste)' if r.get('redirecionado_para') else ''}.")


if __name__ == "__main__":
    main()

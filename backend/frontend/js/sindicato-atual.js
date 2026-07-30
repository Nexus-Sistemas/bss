/*
 * sindicato-atual.js — FILTRO opcional de sindicato para o perfil `sindicato`.
 *
 * Espelha empresa-atual.js. Um contato de sindicato pode administrar VÁRIOS
 * sindicatos (bss.usuario_sindicato é N:N) e vê TODOS por padrão, somados, com
 * o sindicato como coluna. Este seletor só ESTREITA para um sindicato quando o
 * usuário quer — nunca é "sindicato atual" obrigatório.
 *
 * O backend aplica ids_sindicato (escopo inteiro) sempre; id_sindicato (este
 * filtro) é opcional. Sem escolha, não manda nada e vê tudo.
 *
 * Uso:
 *   await montarSeletorSindicato("#seletor-sindicato", () => recarregar());
 *   comSindicatoAtual(params);   // só acrescenta id_sindicato se houver escolha
 *
 * Perfis não-sindicato não filtram por aqui: o seletor não é renderizado e
 * sindicatoAtualId() devolve null.
 */

const SINDICATO_ATUAL_KEY = "bss_sindicato_atual";

let _sindicatosDoUsuario = null;   // cache por página: [{id, razao_social, cnpj}]


function _temEscopoSindicato() {
  const u = usuarioAtual();
  return !!u && u.perfil === "sindicato" && (u.sindicatos || []).length > 0;
}


function sindicatoAtualId() {
  const u = usuarioAtual();
  if (!_temEscopoSindicato()) return null;
  const guardado = parseInt(localStorage.getItem(SINDICATO_ATUAL_KEY) || "", 10);
  if (guardado && u.sindicatos.includes(guardado)) return guardado;
  return null;   // sem filtro = todos os sindicatos do usuário
}


function definirSindicatoAtual(id) {
  if (!id) localStorage.removeItem(SINDICATO_ATUAL_KEY);
  else localStorage.setItem(SINDICATO_ATUAL_KEY, String(id));
}


function comSindicatoAtual(params) {
  const id = sindicatoAtualId();
  if (id) params.set("id_sindicato", id);
  return params;
}


async function _carregarSindicatos() {
  if (_sindicatosDoUsuario) return _sindicatosDoUsuario;
  const r = await apiFetch("/sindicatos?por_pagina=200&ordem=razao_social");
  _sindicatosDoUsuario = r.linhas || [];
  return _sindicatosDoUsuario;
}


async function montarSeletorSindicato(seletorContainer, onChange) {
  const box = document.querySelector(seletorContainer);
  if (!box) return;

  if (!_temEscopoSindicato()) {
    // Não limpa o box: pode estar sendo compartilhado com o seletor de empresa.
    return;
  }

  let sinds;
  try {
    sinds = await _carregarSindicatos();
  } catch (e) {
    box.innerHTML = `<span class="text-xs text-rose-600">Erro ao carregar sindicatos</span>`;
    return;
  }

  if (sinds.length <= 1) {
    box.innerHTML = sinds.length
      ? `<span class="text-sm text-slate-600 truncate max-w-xs" title="${sinds[0].razao_social}">${sinds[0].razao_social}</span>`
      : "";
    return;
  }

  const atual = sindicatoAtualId();
  const opcoes =
    `<option value=""${atual ? "" : " selected"}>Todos os meus sindicatos (${sinds.length})</option>` +
    sinds.map((s) => {
      const sel = s.id === atual ? " selected" : "";
      return `<option value="${s.id}"${sel}>${s.razao_social}</option>`;
    }).join("");

  box.innerHTML = `
    <label class="flex items-center gap-2">
      <span class="text-xs text-slate-400 uppercase tracking-wider whitespace-nowrap">Sindicato</span>
      <select id="sel-sindicato-atual"
              class="text-sm border border-slate-300 rounded-lg px-2 py-1.5 bg-white
                     max-w-md truncate focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500">
        ${opcoes}
      </select>
    </label>
  `;

  document.getElementById("sel-sindicato-atual").addEventListener("change", (ev) => {
    definirSindicatoAtual(parseInt(ev.target.value, 10) || null);
    if (typeof onChange === "function") onChange();
  });
}

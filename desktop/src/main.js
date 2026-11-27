import { Command } from '@tauri-apps/plugin-shell';
import './style.css';

const board = document.querySelector('#board');
const events = document.querySelector('#events');
const hand = document.querySelector('#hand');
const prompt = document.querySelector('#prompt');
const actions = document.querySelector('#actions');

let child;
let revision = 0;
let pending = false;
let refreshTimer;

function send(kind, value = '') {
  if (!child || pending) return;
  pending = true;
  child.write(JSON.stringify({ revision, kind, value }) + '\n').catch((error) => {
    pending = false;
    prompt.textContent = String(error);
  });
}

function button(label, onClick, disabled = false) {
  const element = document.createElement('button');
  element.textContent = label;
  element.disabled = disabled;
  element.addEventListener('click', onClick);
  return element;
}

function render(state) {
  const focusedId = document.activeElement?.dataset.action;
  revision = state.revision;
  pending = false;
  const report = state.screen === 'MatchReportScreen';
  board.hidden = state.opponents.length === 0 && !report;
  document.querySelector('#seat').textContent = state.hp === null ? '' : `你 · 体力 ${state.hp}/${state.maxHp}`;
  document.querySelector('#opponent').textContent = state.opponents.map(
    (opponent) => `${opponent.name} · 体力 ${opponent.hp}/${opponent.maxHp} · ${opponent.handCount} 张手牌`,
  ).join('　');
  events.replaceChildren(...state.events.map((event) => {
    const row = document.createElement('li');
    row.textContent = String(event.message);
    return row;
  }));
  if (!report) events.scrollTop = events.scrollHeight;
  hand.replaceChildren(...state.hand.map((card, index) => {
    const key = String(index + 1 === 10 ? 0 : index + 1);
    const element = button(`${key}　${card.suit}${card.number}\n${card.label}`,
      () => send('key', key), !state.canPlay || index >= 10);
    element.className = 'card';
    element.dataset.action = `card-${key}`;
    return element;
  }));
  prompt.textContent = state.prompts.join(' · ');
  const choices = state.buttons.filter(({ id }) => !['btn-skill', 'btn-play'].includes(id));
  actions.replaceChildren(...choices.map(({ id, label, disabled }) => {
    const element = button(label, () => send('button', id), disabled);
    element.dataset.action = id;
    return element;
  }));
  if (focusedId) {
    const matching = [...document.querySelectorAll('button')].find(
      (element) => element.dataset.action === focusedId && !element.disabled,
    );
    matching?.focus();
  }
  clearTimeout(refreshTimer);
  if (state.screen === 'GamePlayScreen' && !state.canPlay) {
    refreshTimer = setTimeout(() => send('refresh'), 400);
  }
}

const command = Command.sidecar('binaries/practice-engine', ['--desktop-practice']);
command.stdout.on('data', (line) => {
  try {
    const state = JSON.parse(line);
    if (state.protocol !== 1) throw new Error('练习程序的协议版本不兼容。');
    if (state.error) throw new Error(state.error);
    render(state);
  } catch (error) {
    pending = false;
    prompt.textContent = String(error);
  }
});
command.on('error', (error) => {
  prompt.textContent = String(error);
});
command.on('close', () => {
  child = undefined;
  clearTimeout(refreshTimer);
  actions.replaceChildren();
  prompt.textContent = '练习程序已退出。';
});
try {
  child = await command.spawn();
} catch (error) {
  prompt.textContent = String(error);
}

window.addEventListener('keydown', (event) => {
  const key = event.key.toLowerCase();
  if (!/^[0-9e]$/.test(key) && key !== 'escape') return;
  event.preventDefault();
  send('key', key);
});
window.addEventListener('pagehide', () => {
  if (child) void child.kill().catch(() => {});
});

// Presentation only: recording fields, identifiers and exported evidence stay intact.
export const sourceLabel = (source) => source === "baseline" ? "Эталон" : "Новый прогон";
export const statusLabel = (status) => ({
  PASS: "Успешно", FAIL: "Сбой", TIMEOUT: "Таймаут",
  INFRA_ERROR: "Ошибка среды", REGRESSION: "Регрессия",
}[status] ?? status);
export const eventLabel = (type) => ({
  START: "Старт", REPLAN: "Перестроение пути", STUCK: "Застревание",
  RECOVERY: "Восстановление", GOAL: "Цель достигнута", FAIL: "Сбой",
}[type] ?? type);
export const displayLabel = (label) => ({
  "Demo candidate": "Демонстрационный прогон",
  "Demo baseline": "Демонстрационный эталон",
  "Candidate recording": "Новый прогон",
  "Baseline recording": "Эталонная запись",
}[label] ?? label);
export const formatTime = (value) => value.toLocaleString("ru-RU", {
  minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false,
});
export const displayUnit = (unit) => ({ m: "м", s: "с", percent: "%", count: "" }[unit] ?? unit);
export const eventTitle = (event) => `${eventLabel(event.type)}${event.count > 1 ? ` · +${event.count.toLocaleString("ru-RU")}` : ""}`;

const messages = {
  SUCCEEDED: "Навигация успешно завершена",
  FAILED: "Навигация завершилась с ошибкой",
  CANCELED: "Навигация отменена",
  CANCELED_BY_TIMEOUT: "Навигация остановлена по таймауту",
  GOAL_REJECTED: "Цель отклонена",
  UNKNOWN: "Результат навигации неизвестен",
  "Navigation started": "Навигация началась",
  "Local planner stopped making progress": "Локальный планировщик перестал продвигаться к цели",
  "Recovery behavior completed": "Восстановление завершено",
  "No movement observed within the stuck window":
    "За окно обнаружения застревания не наблюдалось перемещения выше порога. При отсутствии обратной связи это не доказывает остановку робота.",
  "Nav2 recovery counter increased":
    "Nav2 сообщил о росте счётчика восстановлений. Отмечено время получения данных; точное время отдельных действий неизвестно.",
  "Goal reached": "Цель достигнута",
  "Synthetic baseline started": "Запущен демонстрационный эталон",
  "Synthetic baseline reached the goal": "Демонстрационный эталон достиг цели",
  "The recordings describe different scenarios.": "Записи относятся к разным сценариям.",
  "The recordings use different coordinate frames.": "У записей разные системы координат.",
  "The recordings have different start positions.": "У записей разные начальные положения.",
  "The recordings have different goal positions.": "У записей разные целевые положения.",
  "Replay files show recorded behavior. A verified gate requires suite results.":
    "Записи показывают поведение робота. Для проверки регрессий нужны результаты набора сценариев.",
  "Open a baseline suite to evaluate the regression gate.":
    "Откройте эталонный набор результатов, чтобы проверить регрессии.",
  "No trajectory was recorded for this result. Metrics are still available.":
    "Для этого результата нет записи траектории. Метрики по-прежнему доступны.",
};
export const eventMessage = (message) => messages[message] ?? message ?? "Записанное событие";
export function noticeText(message) {
  if (!message) return "";
  if (messages[message]) return messages[message];
  if (message.startsWith("Gate unavailable:"))
    return "Проверка регрессий недоступна: результаты не прошли проверку совместимости. Проверьте статусы, сценарии и параметры среды. Техническая причина доступна в подсказке.";
  if (message.startsWith("Trajectory unavailable:"))
    return "Траектория недоступна: запись не прошла проверку или не соответствует результату. Метрики доступны. Техническая причина доступна в подсказке.";
  return message;
}

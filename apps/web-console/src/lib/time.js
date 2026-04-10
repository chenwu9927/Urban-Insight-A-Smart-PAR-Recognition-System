export function parseServerDate(value) {
    if (!value) return null;
    if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;

    const raw = String(value).trim();
    if (!raw) return null;

    const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(raw) ? raw : `${raw}Z`;
    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatDateTime(value, options = {}) {
    if (!value) return '--';
    const parsed = parseServerDate(value);
    if (!parsed) return String(value);

    return parsed.toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        hour12: false,
        ...options,
    });
}

export function toTimestamp(value) {
    return parseServerDate(value)?.getTime() ?? 0;
}

export function formatDateInputValue(value = new Date(), timeZone = 'Asia/Shanghai') {
    const parsed = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(parsed.getTime())) return '';

    const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
    }).formatToParts(parsed);
    const map = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${map.year}-${map.month}-${map.day}`;
}

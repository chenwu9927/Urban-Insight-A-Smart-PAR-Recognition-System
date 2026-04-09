export const POLL_INTERVAL_MS = 5000;
export const ACTIVE_POLL_INTERVAL_MS = 1500;

export function formatDateTime(value) {
    if (!value) return '--';
    try {
        return new Date(value).toLocaleString('zh-CN');
    } catch {
        return value;
    }
}

export function getMessageText(message) {
    if (!message) return '';
    const content = message.content;
    if (typeof content === 'string') return content;
    if (content && typeof content.text === 'string' && content.text.trim()) return content.text.trim();
    if (content && typeof content.error_message === 'string' && content.error_message.trim()) {
        return content.error_message.trim();
    }
    if (content && content.answer) return String(content.answer);
    if (content && content.output_payload) return JSON.stringify(content.output_payload, null, 2);
    if (content) return JSON.stringify(content, null, 2);
    return '';
}

export function getSessionTitle(session) {
    return session?.title?.trim() || `会话 ${session?.id?.slice(0, 8) || ''}`;
}

export function getSummaryText(summary) {
    if (!summary) return '暂无摘要。';
    if (typeof summary === 'string') return summary;
    try {
        return JSON.stringify(summary, null, 2);
    } catch {
        return String(summary);
    }
}

export function sortSessions(items) {
    return [...items].sort((left, right) => {
        const leftValue = new Date(left.last_run_at || left.updated_at || 0).getTime();
        const rightValue = new Date(right.last_run_at || right.updated_at || 0).getTime();
        return rightValue - leftValue;
    });
}

export function translateSource(value) {
    const mapping = {
        web: '网页',
        email: '邮件',
        scheduled_task: '巡检',
        manual: '手动',
        memory: '记忆',
    };
    return mapping[value] || value || '--';
}

export function translateRunStatus(value) {
    const mapping = {
        queued: '排队中',
        claimed: '已领取',
        running: '运行中',
        waiting_approval: '待审批',
        waiting_input: '待输入',
        completed: '已完成',
        failed: '失败',
        cancelled: '已取消',
        expired: '已过期',
    };
    return mapping[value] || value || '--';
}

export function translateApprovalStatus(value) {
    const mapping = {
        pending: '待处理',
        approved: '已批准',
        rejected: '已拒绝',
    };
    return mapping[value] || value || '--';
}

export function translateLoopHealth(value) {
    const mapping = {
        healthy: '正常',
        degraded: '降级',
        disabled: '已停用',
        down: '已停止',
        starting: '启动中',
        stopping: '停止中',
    };
    return mapping[value] || value || '--';
}

export function translateLoopName(value) {
    const mapping = {
        runtime: '执行循环',
        scheduler: '调度循环',
        email: '邮件循环',
    };
    return mapping[value] || value || '--';
}

export function translateScheduleMode(value) {
    const mapping = {
        immediate: '即时',
        scheduled: '定时',
        event: '事件触发',
        proactive: '主动任务',
        replan: '重新规划',
        goal_recovery: '目标恢复',
        verification: '验证',
    };
    return mapping[value] || value || '--';
}

export function translateAlertStatus(value) {
    const mapping = {
        open: '未恢复',
        resolved: '已恢复',
    };
    return mapping[value] || value || '--';
}

export function translateSeverity(value) {
    const mapping = {
        info: '提示',
        warning: '警告',
        critical: '严重',
    };
    return mapping[value] || value || '--';
}

export function isRunActive(run) {
    return ['queued', 'claimed', 'running', 'waiting_approval', 'waiting_input'].includes(run?.status);
}

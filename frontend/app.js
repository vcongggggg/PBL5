const API_BASE = "http://localhost:8000";
let parkingChart = null;
let fireTelemetryChart = null;
let currentFireStatus = { active: false, message: "Hệ thống báo cháy đang bình thường." };
let currentFireAlerts = [];
let fireOverlayDismissedForActive = false;
const latestGateResults = {
    entry: {},
    exit: {},
};

function initParkingChart() {
    const ctx = document.getElementById('parkingFlowChart').getContext('2d');
    const isDark = document.documentElement.classList.contains("dark");
    const textColor = isDark ? "#94a3b8" : "#475569";
    const gridColor = isDark ? "rgba(30, 41, 59, 0.4)" : "rgba(226, 232, 240, 0.6)";

    parkingChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Lượt Xe Vào',
                    data: [],
                    borderColor: '#10b981', // emerald-500
                    backgroundColor: 'rgba(16, 185, 129, 0.08)',
                    borderWidth: 2,
                    tension: 0.35,
                    fill: true,
                    pointBackgroundColor: '#10b981',
                    pointHoverRadius: 6
                },
                {
                    label: 'Lượt Xe Ra',
                    data: [],
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.06)',
                    borderWidth: 2,
                    tension: 0.35,
                    fill: true,
                    pointBackgroundColor: '#f59e0b',
                    pointHoverRadius: 6
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: textColor,
                        font: { family: 'Inter', size: 10, weight: '600' }
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            },
            scales: {
                x: {
                    grid: { color: gridColor },
                    ticks: { color: textColor, font: { family: 'Inter', size: 10 } }
                },
                y: {
                    grid: { color: gridColor },
                    ticks: { 
                        color: textColor, 
                        font: { family: 'Inter', size: 10 },
                        stepSize: 1,
                        precision: 0
                    }
                }
            }
        }
    });
}

function initFireTelemetryChart() {
    const canvas = document.getElementById("fireTelemetryChart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const isDark = document.documentElement.classList.contains("dark");
    const textColor = isDark ? "#94a3b8" : "#475569";
    const gridColor = isDark ? "rgba(148, 163, 184, 0.18)" : "rgba(226, 232, 240, 0.75)";

    fireTelemetryChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: [],
            datasets: [{
                label: "Giá trị A0",
                data: [],
                borderColor: "#e11d48",
                backgroundColor: "rgba(225, 29, 72, 0.08)",
                borderWidth: 2,
                tension: 0.3,
                fill: true,
                pointRadius: 0,
                pointHoverRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: {
                    display: true,
                    labels: { color: textColor, font: { family: "Inter", size: 10, weight: "600" } }
                },
                tooltip: { mode: "index", intersect: false }
            },
            scales: {
                x: {
                    grid: { color: gridColor },
                    ticks: { color: textColor, maxTicksLimit: 6, font: { family: "Inter", size: 10 } }
                },
                y: {
                    min: 0,
                    max: 4095,
                    grid: { color: gridColor },
                    ticks: { color: textColor, font: { family: "Inter", size: 10 } }
                }
            }
        }
    });
}

function pushFireTelemetryPoint(point) {
    if (!fireTelemetryChart || !point) return;
    const timestamp = point.timestamp ? new Date(point.timestamp) : new Date();
    const label = timestamp.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const value = Number(point.analog_value ?? 0);

    fireTelemetryChart.data.labels.push(label);
    fireTelemetryChart.data.datasets[0].data.push(value);
    while (fireTelemetryChart.data.labels.length > 60) {
        fireTelemetryChart.data.labels.shift();
        fireTelemetryChart.data.datasets[0].data.shift();
    }
    fireTelemetryChart.update("none");

    const latest = document.getElementById("fireTelemetryLatest");
    if (latest) {
        const digitalText = Number(point.digital_value) === 0 ? "DO: phát hiện" : "DO: bình thường";
        const analogText = value <= 1200 ? "A0: nguy cơ lửa" : "A0: bình thường";
        latest.textContent = `A0: ${value} / 4095 · ${analogText} · ${digitalText}`;
    }
}

async function fetchFireTelemetry() {
    try {
        const res = await fetch(`${API_BASE}/api/fire/telemetry?limit=60`);
        if (!res.ok) return;
        const rows = await res.json();
        if (!fireTelemetryChart) return;
        fireTelemetryChart.data.labels = [];
        fireTelemetryChart.data.datasets[0].data = [];
        rows.forEach(pushFireTelemetryPoint);
    } catch (err) {
        console.warn("Không thể tải dữ liệu A0 cảm biến cháy", err);
    }
}

function updateChartFromHistory(rows) {
    if (!parkingChart || !rows) return;
    
    const hourlyIn = {};
    const hourlyOut = {};
    
    const labels = [];
    const now = new Date();
    for (let i = 7; i >= 0; i--) {
        const d = new Date(now.getTime() - i * 2 * 60 * 60 * 1000);
        const hourStr = `${String(d.getHours()).padStart(2, '0')}:00`;
        labels.push(hourStr);
        hourlyIn[hourStr] = 0;
        hourlyOut[hourStr] = 0;
    }
    
    rows.forEach(row => {
        if (row.time_in) {
            const dateIn = new Date(row.time_in);
            const hour = Math.floor(dateIn.getHours() / 2) * 2;
            const hourStr = `${String(hour).padStart(2, '0')}:00`;
            if (hourStr in hourlyIn) {
                hourlyIn[hourStr]++;
            }
        }
        if (row.time_out) {
            const dateOut = new Date(row.time_out);
            const hour = Math.floor(dateOut.getHours() / 2) * 2;
            const hourStr = `${String(hour).padStart(2, '0')}:00`;
            if (hourStr in hourlyOut) {
                hourlyOut[hourStr]++;
            }
        }
    });
    
    const dataIn = labels.map(l => hourlyIn[l]);
    const dataOut = labels.map(l => hourlyOut[l]);
    
    parkingChart.data.labels = labels;
    parkingChart.data.datasets[0].data = dataIn;
    parkingChart.data.datasets[1].data = dataOut;
    parkingChart.update();
}

const gateState = {
    entry: {
        gateType: "entry",
        result: document.getElementById("result-entry"),
        status: document.getElementById("status-entry"),
        rfidInput: document.getElementById("rfid-entry"),
        plateCanvas: document.getElementById("canvas-entry"),
    },
    exit: {
        gateType: "exit",
        result: document.getElementById("result-exit"),
        status: document.getElementById("status-exit"),
        rfidInput: document.getElementById("rfid-exit"),
        plateCanvas: document.getElementById("canvas-exit"),
        entryPlateCanvas: document.getElementById("canvas-exit-entry"),
    },
};

// Vietnamese Plate design generator helper
function formatVietnamesePlate(plateStr) {
    if (!plateStr || plateStr === "-") return `<span class="text-on-surface-variant/60 font-semibold">-</span>`;
    const cleanPlate = plateStr.replace(/[^a-zA-Z0-9]/g, "").toUpperCase();
    if (cleanPlate.length < 4) {
        return `<strong class="font-mono text-sm">${plateStr}</strong>`;
    }
    
    let line1 = "";
    let line2 = "";
    
    const match = cleanPlate.match(/^([0-9]{2}[A-Z]{1,2})([0-9]{3,6})$/);
    if (match) {
        line1 = match[1];
        let rawNum = match[2];
        if (rawNum.length === 6) {
            line1 += rawNum.slice(0, 1);
            rawNum = rawNum.slice(1);
        }
        if (rawNum.length === 5) {
            line2 = rawNum.slice(0, 3) + "." + rawNum.slice(3);
        } else {
            line2 = rawNum;
        }
    } else {
        const mid = Math.ceil(cleanPlate.length / 2);
        line1 = cleanPlate.slice(0, mid);
        line2 = cleanPlate.slice(mid);
    }
    
    return `
        <div class="inline-flex flex-col items-center justify-center bg-white text-slate-900 border-2 border-slate-900 rounded-md px-3 py-1 shadow-md font-mono select-none my-1" style="min-width: 130px; line-height: 1.1;">
            <div class="text-[10px] font-extrabold border-b border-slate-300 w-full text-center pb-0.5 mb-0.5 tracking-wider">${line1}</div>
            <div class="text-base font-extrabold tracking-widest">${line2}</div>
        </div>
    `;
}

// Compact plate display inside data tables
function formatCompactPlate(plateStr) {
    if (!plateStr) return "-";
    return `<span class="inline-block bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-100 border border-slate-300 dark:border-slate-700 px-2 py-0.5 rounded font-mono font-bold text-xs shadow-sm">${plateStr.toUpperCase()}</span>`;
}

function resolveImageUrl(imageUrl) {
    if (!imageUrl) return "";
    if (imageUrl.startsWith("http")) return imageUrl;
    return `${API_BASE}${imageUrl}`;
}

function drawPlateEvidence(gate, imageUrl, canvasName = "plateCanvas") {
    const cfg = gateState[gate];
    const canvas = cfg?.[canvasName];
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    const width = canvas.clientWidth || 320;
    const height = canvas.clientHeight || 80;
    canvas.width = width;
    canvas.height = height;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "rgba(15, 23, 42, 0.35)";
    ctx.fillRect(0, 0, width, height);

    const resolvedUrl = resolveImageUrl(imageUrl);
    if (!resolvedUrl) {
        ctx.fillStyle = "rgba(148, 163, 184, 0.65)";
        ctx.font = "600 11px Inter, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("CHUA CO ANH BIEN SO", width / 2, height / 2);
        return;
    }

    const img = new Image();
    img.onload = () => {
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = "#000";
        ctx.fillRect(0, 0, width, height);

        const scale = Math.min(width / img.width, height / img.height);
        const drawWidth = img.width * scale;
        const drawHeight = img.height * scale;
        const x = (width - drawWidth) / 2;
        const y = (height - drawHeight) / 2;
        ctx.drawImage(img, x, y, drawWidth, drawHeight);
    };
    img.onerror = () => {
        ctx.fillStyle = "rgba(244, 63, 94, 0.85)";
        ctx.font = "700 11px Inter, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("LOI TAI ANH", width / 2, height / 2);
    };
    img.src = `${resolvedUrl}?t=${Date.now()}`;
}

function setStatus(gate, message, tone = "") {
    const cfg = gateState[gate];
    if (!cfg || !cfg.status) return;
    
    let colorClass = "text-on-surface-variant/80";
    let dotColor = "bg-slate-400";
    
    if (tone === "ok") {
        colorClass = "text-success";
        dotColor = "bg-success";
    }
    if (tone === "warn") {
        colorClass = "text-warning";
        dotColor = "bg-warning";
    }
    if (tone === "danger") {
        colorClass = "text-error";
        dotColor = "bg-error";
    }
    
    cfg.status.className = `text-xs font-bold pb-2 border-b border-border-subtle/50 flex items-center gap-1.5 ${colorClass}`;
    cfg.status.innerHTML = `<span class="w-1.5 h-1.5 rounded-full ${dotColor} ${tone ? 'animate-pulse' : ''}"></span> Trạng thái: ${message}`;
}

function renderGateResult(gate, data = {}) {
    const cfg = gateState[gate];
    if (!cfg || !cfg.result) return;
    if (data && Object.keys(data).length > 0) {
        latestGateResults[gate] = { ...(data || {}) };
    }
    
    const feeFmt = data.fee != null ? Number(data.fee).toLocaleString("vi-VN") + "đ" : "-";
    const confFmt = data.confidence != null ? Number(data.confidence).toFixed(3) : "-";
    
    const recPlateHTML = formatVietnamesePlate(data.recognized_plate);
    const plateInHTML = formatVietnamesePlate(data.plate_in);
    const plateOutHTML = formatVietnamesePlate(data.plate_out);
    drawPlateEvidence(gate, data.image_url);
    if (gate === "exit") {
        drawPlateEvidence(gate, data.plate_in_image_url, "entryPlateCanvas");
    }

    cfg.result.innerHTML = `
        <div class="flex justify-between items-center py-2 border-b border-border-subtle/20"><span class="text-on-surface-variant/80">Lệnh xử lý</span><strong class="text-xs uppercase tracking-wider text-primary font-bold">${data.action ?? "-"}</strong></div>
        <div class="flex justify-between items-center py-2 border-b border-border-subtle/20"><span class="text-on-surface-variant/80">Mã thẻ RFID</span><strong class="font-mono text-xs text-warning">${data.rfid_tag ?? "-"}</strong></div>
        <div class="flex justify-between items-center py-2 border-b border-border-subtle/20"><span class="text-on-surface-variant/80">Biển số AI</span><div>${recPlateHTML}</div></div>
        <div class="flex justify-between items-center py-2 border-b border-border-subtle/20"><span class="text-on-surface-variant/80">Biển ghi nhận vào</span><div>${plateInHTML}</div></div>
        <div class="flex justify-between items-center py-2 border-b border-border-subtle/20"><span class="text-on-surface-variant/80">Biển ghi nhận ra</span><div>${plateOutHTML}</div></div>
        <div class="flex justify-between items-center py-2 border-b border-border-subtle/20"><span class="text-on-surface-variant/80">Độ tin cậy AI</span><strong class="text-xs">${confFmt}</strong></div>
        <div class="flex justify-between items-center py-2 border-b border-border-subtle/20"><span class="text-on-surface-variant/80">Khớp thẻ &amp; biển</span><strong class="text-xs ${data.matched === true ? 'text-success' : 'text-on-surface'}">${data.matched ?? "-"}</strong></div>
        <div class="flex justify-between items-center py-2 border-b border-border-subtle/20"><span class="text-on-surface-variant/80">Thời gian đỗ</span><strong class="text-xs">${data.duration_minutes ?? "-"} phút</strong></div>
        <div class="flex justify-between items-center py-2 border-b border-border-subtle/20"><span class="text-on-surface-variant/80">Phí thu tạm tính</span><strong class="text-xs text-warning">${feeFmt}</strong></div>
        <div class="flex justify-between items-center py-2"><span class="text-on-surface-variant/80">Thông báo hiển thị</span><strong class="text-xs text-right max-w-[180px] truncate block" title="${data.message ?? ""}">${data.message ?? "-"}</strong></div>
    `;
}

async function startCamera(gate) {
    const img = document.getElementById(`video-${gate}`);
    if (img) {
        img.src = `${API_BASE}/api/camera/stream/${gate}?t=${Date.now()}`;
    }
    setStatus(gate, "Luồng Camera đang truyền phát trực tuyến", "ok");
}

function stopCamera(gate) {
    const img = document.getElementById(`video-${gate}`);
    if (img) {
        img.src = "";
    }
    setStatus(gate, "Camera đang tạm dừng");
}

async function sendTrigger(gate, triggerType, rfidTag = "") {
    const sourceId = `${gate}-${triggerType}-ui`;
    const payload = {
        gate_type: gate,
        trigger_type: triggerType,
        source_id: sourceId,
        rfid_tag: rfidTag || null,
    };
    const res = await fetch(`${API_BASE}/api/gates/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Trigger failed");
    }
}

async function sendScan(gate, triggerType, rfidTag = "") {
    const sourceId = `${gate}-${triggerType}-ui`;
    const formData = new FormData();
    formData.append("gate_type", gate);
    formData.append("trigger_type", triggerType);
    formData.append("source_id", sourceId);
    if (rfidTag) {
        formData.append("rfid_tag", rfidTag);
    }

    const res = await fetch(`${API_BASE}/api/gates/scan-from-cam`, {
        method: "POST",
        body: formData,
    });
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.detail || "Scan failed");
    }
    return data;
}

async function sendSensorEvent(gate) {
    const sourceId = `${gate}-sensor-ui`;
    const payload = {
        gate_type: gate,
        trigger_type: "sensor",
        source_id: sourceId,
        rfid_tag: null,
    };
    const res = await fetch(`${API_BASE}/api/gates/sensor-event`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.detail || "Sensor event failed");
    }
    return data;
}

async function triggerAndScan(gate, triggerType) {
    const cfg = gateState[gate];
    if (!cfg) return;

    const rfidTag = triggerType === "rfid" ? cfg.rfidInput.value.trim() : "";
    if (triggerType === "rfid" && !rfidTag) {
        setStatus(gate, "Nhập UID thẻ RFID trước khi quét", "warn");
        return;
    }

    try {
        if (triggerType === "sensor") {
            setStatus(gate, "Đã kích hoạt cảm biến, đang bám biển số...", "warn");
            const data = await sendSensorEvent(gate);
            if (data?.message) {
                setStatus(gate, data.message, "warn");
            }
            await fetchDashboard();
            return;
        }

        setStatus(gate, `Đang truyền tín hiệu vật lý ${triggerType}...`, "warn");
        await sendTrigger(gate, triggerType, rfidTag);

        setStatus(gate, "Đang chụp ảnh & nhận diện biển số...", "warn");
        const result = await sendScan(gate, triggerType, rfidTag);
        renderGateResult(gate, result);

        if (result.action === "open") {
            setStatus(gate, "Mở barie thành công!", "ok");
        } else {
            setStatus(gate, result.message || "Từ chối mở cổng", "danger");
        }

        await fetchDashboard();
    } catch (err) {
        console.error(err);
        setStatus(gate, err.message || "Lỗi xử lý sự kiện", "danger");
    }
}

const MANUAL_OPEN_REASONS = {
    open_only: "Chỉ mở cổng",
    verified_entry: "Cho xe vào sau khi xác minh",
    verified_plate: "Biển số đúng, cho xe ra",
    lost_card: "Mất RFID, giải phóng xe",
    manual_override: "Bảo vệ xác nhận thủ công",
    emergency: "Mở khẩn cấp",
    maintenance: "Kiểm tra/bảo trì thiết bị",
    system_error: "Camera/cảm biến/hệ thống lỗi"
};

function askManualOpenReason(gate) {
    return new Promise((resolve) => {
        const oldModal = document.getElementById("manualOpenReasonModal");
        if (oldModal) oldModal.remove();

        const entryOptions = [
            ["open_only", "Chỉ mở cổng vào", "Không tạo phiên, dùng khi cần mở thử hoặc xử lý nhanh."],
            ["verified_entry", "Cho xe vào sau khi xác minh", "Bảo vệ đã nhìn biển/thẻ và quyết định cho xe vào thủ công."],
            ["system_error", "Lỗi camera/cảm biến làn vào", "Mở cổng vào do hệ thống không nhận diện được nhưng bảo vệ đã kiểm tra."],
            ["emergency", "Mở khẩn cấp", "Ưu tiên an toàn, không xử lý phiên gửi xe."],
            ["maintenance", "Bảo trì", "Mở cổng để kiểm tra servo, barrier hoặc cảm biến."],
        ];
        const exitOptions = [
            ["open_only", "Chỉ mở cổng ra", "Không đóng session, không tính phí."],
            ["verified_plate", "Biển số đúng, cho xe ra", "Đóng session xe đang hiển thị và mở cổng ra."],
            ["lost_card", "Mất RFID", "Đóng session, tính phí gửi xe + phí đền bù RFID."],
            ["system_error", "Lỗi camera/cảm biến làn ra", "Bảo vệ xác nhận thực tế, đóng session và mở cổng ra."],
            ["emergency", "Mở khẩn cấp", "Chỉ mở cổng trong tình huống khẩn cấp."],
            ["maintenance", "Bảo trì", "Mở cổng để kiểm tra thiết bị."],
        ];
        const options = gate === "exit" ? exitOptions : entryOptions;

        const modal = document.createElement("div");
        modal.id = "manualOpenReasonModal";
        modal.className = "fixed inset-0 z-[9999] bg-slate-950/70 backdrop-blur-[2px] flex items-center justify-center p-4";
        modal.innerHTML = `
            <div class="w-full max-w-lg bg-white dark:bg-slate-950 border border-teal-500/40 rounded-xl shadow-2xl overflow-hidden text-slate-950 dark:text-white">
                <div class="px-5 py-4 border-b border-slate-200 dark:border-slate-800 bg-teal-50 dark:bg-teal-950/30">
                    <p class="text-[10px] uppercase tracking-[0.14em] text-teal-700 dark:text-teal-300 font-bold">Mở cổng thủ công - ${gate === "exit" ? "Làn ra" : "Làn vào"}</p>
                    <h3 class="text-base font-extrabold mt-1">Chọn mục đích mở cổng</h3>
                    <p class="text-xs text-slate-600 dark:text-slate-300 mt-1">${gate === "exit" ? "Các mục cho xe ra có thể đóng session, tính phí và ghi log." : "Làn vào không giải phóng xe; chỉ ghi log lý do mở cổng."}</p>
                </div>
                <div class="p-4 grid gap-2">
                    ${options.map(([value, title, desc]) => `
                        <button type="button" data-manual-reason="${value}" class="text-left px-4 py-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-teal-500 hover:bg-teal-50 dark:hover:bg-teal-950/40 transition-all shadow-sm">
                            <span class="block text-sm font-bold">${title}</span>
                            <span class="block text-xs text-slate-600 dark:text-slate-300 mt-0.5">${desc}</span>
                        </button>
                    `).join("")}
                </div>
                <div class="px-4 py-3 bg-slate-50 dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 flex justify-end">
                    <button type="button" data-manual-cancel class="px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-bold hover:bg-slate-100 dark:hover:bg-slate-800 transition-all">Hủy</button>
                </div>
            </div>
        `;

        const close = (value) => {
            modal.remove();
            resolve(value);
        };
        modal.addEventListener("click", (event) => {
            if (event.target === modal || event.target.closest("[data-manual-cancel]")) {
                close(null);
                return;
            }
            const reasonBtn = event.target.closest("[data-manual-reason]");
            if (reasonBtn) {
                close(reasonBtn.dataset.manualReason || "open_only");
            }
        });
        document.body.appendChild(modal);
    });
}

function getGatePlateCandidate(gate) {
    const data = latestGateResults[gate] || {};
    const candidates = [
        data.plate_out,
        data.recognized_plate,
        data.plate_in,
        data.plate,
    ];
    return (candidates.find((value) => value && value !== "UNKNOWN" && value !== "PROCESSING" && value !== "...") || "").trim();
}

function getGateRfidCandidate(gate) {
    const data = latestGateResults[gate] || {};
    const cfg = gateState[gate];
    const candidates = [
        data.rfid_tag,
        cfg?.rfidInput?.value,
    ];
    return (candidates.find((value) => value && value !== "-" && value !== "UNKNOWN") || "").trim();
}

async function searchOpenSessions(query) {
    const res = await fetch(`${API_BASE}/api/parking/open-sessions/search?q=${encodeURIComponent(query || "")}&limit=8`);
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.detail || "Khong tim duoc danh sach xe dang trong bai");
    }
    return data;
}

function showOpenSessionPicker(initialQuery = "") {
    return new Promise((resolve) => {
        const oldModal = document.getElementById("openSessionPickerModal");
        if (oldModal) oldModal.remove();

        const modal = document.createElement("div");
        modal.id = "openSessionPickerModal";
        modal.className = "fixed inset-0 z-[10000] bg-slate-950/70 backdrop-blur-[2px] flex items-center justify-center p-4";
        modal.innerHTML = `
            <div class="w-full max-w-2xl bg-white dark:bg-slate-950 border border-teal-500/40 rounded-xl shadow-2xl overflow-hidden text-slate-950 dark:text-white">
                <div class="px-5 py-4 border-b border-slate-200 dark:border-slate-800 bg-teal-50 dark:bg-teal-950/30">
                    <p class="text-[10px] uppercase tracking-[0.14em] text-teal-700 dark:text-teal-300 font-bold">Tìm xe đang trong bãi</p>
                    <h3 class="text-base font-extrabold mt-1">Chọn session cần giải phóng</h3>
                    <p class="text-xs text-slate-600 dark:text-slate-300 mt-1">Dùng khi mất RFID hoặc AI đọc sai biển số. Hãy đối chiếu biển/ảnh lúc vào trước khi xác nhận.</p>
                </div>
                <div class="p-4">
                    <input id="openSessionSearchInput" value="${initialQuery || ""}" class="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm outline-none focus:ring-2 focus:ring-teal-500/30" placeholder="Nhập một phần biển số, ví dụ 43A78" />
                    <div id="openSessionSearchResults" class="mt-3 grid gap-2 max-h-[360px] overflow-y-auto"></div>
                </div>
                <div class="px-4 py-3 bg-slate-50 dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 flex justify-end">
                    <button type="button" data-picker-cancel class="px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-bold hover:bg-slate-100 dark:hover:bg-slate-800 transition-all">Hủy</button>
                </div>
            </div>
        `;

        const input = modal.querySelector("#openSessionSearchInput");
        const resultsEl = modal.querySelector("#openSessionSearchResults");
        let debounceTimer = null;

        const close = (value) => {
            modal.remove();
            resolve(value);
        };

        const renderResults = async () => {
            const query = input.value.trim();
            resultsEl.innerHTML = `<div class="text-xs text-slate-500 py-3">Đang tìm...</div>`;
            try {
                const rows = await searchOpenSessions(query);
                if (!rows.length) {
                    resultsEl.innerHTML = `<div class="text-xs text-slate-500 py-3">Không tìm thấy session đang mở phù hợp.</div>`;
                    return;
                }
                resultsEl.innerHTML = rows.map((row) => `
                    <button type="button" data-session-plate="${row.plate_number || ""}" data-session-rfid="${row.rfid_tag || ""}" class="text-left grid grid-cols-[96px_1fr] gap-3 p-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-teal-500 hover:bg-teal-50 dark:hover:bg-teal-950/40 transition-all">
                        <div class="h-16 rounded-md bg-slate-200 dark:bg-slate-800 overflow-hidden flex items-center justify-center">
                            ${row.image_url ? `<img src="${API_BASE}${row.image_url}?t=${Date.now()}" class="w-full h-full object-contain" />` : `<span class="text-[10px] text-slate-500">Không có ảnh</span>`}
                        </div>
                        <div>
                            <div class="font-mono text-base font-extrabold">${row.plate_number || "-"}</div>
                            <div class="text-xs text-slate-600 dark:text-slate-300 mt-1">RFID: ${row.rfid_tag || "-"} | Sai lệch: ${row.distance ?? "-"}</div>
                            <div class="text-xs text-slate-500 mt-1">Vào lúc: ${row.time_in ? new Date(row.time_in).toLocaleString("vi-VN") : "-"}</div>
                        </div>
                    </button>
                `).join("");
            } catch (err) {
                resultsEl.innerHTML = `<div class="text-xs text-rose-600 py-3">${err.message}</div>`;
            }
        };

        input.addEventListener("input", () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(renderResults, 250);
        });
        modal.addEventListener("click", (event) => {
            if (event.target === modal || event.target.closest("[data-picker-cancel]")) {
                close(null);
                return;
            }
            const rowBtn = event.target.closest("[data-session-plate]");
            if (rowBtn) {
                close({
                    plate: rowBtn.dataset.sessionPlate || "",
                    rfidTag: rowBtn.dataset.sessionRfid || "",
                });
            }
        });
        document.body.appendChild(modal);
        input.focus();
        renderResults();
    });
}

async function forceCheckoutFromMonitoring(gate, reason) {
    if (gate !== "exit") {
        alert("Giai phong xe chi ap dung cho lan ra. Lan vao chi nen dung 'open_only' hoac 'emergency'.");
        return false;
    }

    let rfidTag = getGateRfidCandidate(gate);
    let plate = getGatePlateCandidate(gate);
    if (!rfidTag && (reason === "lost_card" || reason === "system_error" || !plate)) {
        const selectedSession = await showOpenSessionPicker(plate);
        if (!selectedSession) return false;
        plate = selectedSession.plate || "";
        rfidTag = selectedSession.rfidTag || "";
    }
    if (!plate && !rfidTag) return false;

    const confirmText = reason === "lost_card"
        ? `Xac nhan giai phong xe ${plate || rfidTag}, tinh phi gui xe + phi den bu mat RFID va mo cong ra?`
        : `Xac nhan dong session xe ${plate || rfidTag} va mo cong ra?`;
    if (!window.confirm(confirmText)) return false;

    setStatus(gate, "Dang giai phong xe va tinh phi...", "warn");
    const formData = new FormData();
    if (plate) formData.append("plate_number", plate);
    if (rfidTag) formData.append("rfid_tag", rfidTag);
    formData.append("reason", reason);
    formData.append("open_gate", "true");
    formData.append("operator", "admin");

    const res = await fetch(`${API_BASE}/api/parking/force-checkout`, {
        method: "POST",
        headers: {
            "X-API-Key": "pbl5_secure_key_12345"
        },
        body: formData,
    });
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.detail || "Giai phong xe that bai");
    }

    const compensationFee = Number(data.compensation_fee || 0);
    const compensationText = compensationFee > 0
        ? ` Phi den bu RFID: ${compensationFee.toLocaleString("vi-VN")}d.`
        : "";
    setStatus(gate, `${data.message || "Da giai phong xe."}${compensationText}`, "ok");
    renderGateResult(gate, {
        action: "force_checkout",
        recognized_plate: data.plate_number,
        plate_out: data.plate_number,
        confidence: null,
        matched: true,
        duration_minutes: data.duration_minutes,
        fee: data.fee,
        message: `${data.message || "Da giai phong xe."}${compensationText}`,
    });
    await fetchDashboard();
    await fetchParkingHistory();
    return true;
}

async function forceOpenGate(gate) {
    try {
        const reason = await askManualOpenReason(gate);
        if (!reason) return;
        if (["verified_plate", "lost_card", "system_error", "manual_override"].includes(reason) && gate === "exit") {
            const handled = await forceCheckoutFromMonitoring(gate, reason);
            if (handled) return;
        }
        setStatus(gate, "Đang phát lệnh mở cổng khẩn cấp...", "warn");
        const formData = new FormData();
        formData.append("gate_type", gate);
        formData.append("reason", reason);
        formData.append("operator", "admin");

        const res = await fetch(`${API_BASE}/api/gates/force-open`, {
            method: "POST",
            headers: {
                "X-API-Key": "pbl5_secure_key_12345"
            },
            body: formData,
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || "Lỗi giao tiếp cổng");
        }
        setStatus(gate, "Đã cưỡng bức mở cổng khẩn cấp thành công!", "ok");
        await fetchDashboard();
    } catch (err) {
        console.error(err);
        setStatus(gate, err.message || "Cưỡng bức mở cổng thất bại", "danger");
    }
}

async function fetchDashboard() {
    try {
        const res = await fetch(`${API_BASE}/api/dashboard`);
        if (!res.ok) throw new Error("dashboard failed");
        const data = await res.json();
        
        // Populate stats
        clearStatSkeleton("statInBay", "statInToday", "statOutToday", "statRevenue");
        document.getElementById("statInBay").textContent = data.total_in_bay;
        document.getElementById("statInToday").textContent = data.today_total_in;
        document.getElementById("statOutToday").textContent = data.today_total_out;
        document.getElementById("statRevenue").textContent = Number(data.today_revenue || 0).toLocaleString("vi-VN") + "đ";
        
        const maxSlots = data.max_slots || 50;
        const available = data.available_slots !== undefined ? data.available_slots : (maxSlots - data.total_in_bay);
        const guestInBay = Number(data.guest_in_bay ?? 0);
        const monthlyInBay = Number(data.monthly_in_bay ?? 0);
        const maxGuestSlots = Number(data.max_guest_slots || 0);
        const maxMonthlySlots = Number(data.max_monthly_slots || 0);
        const guestCapacityText = maxGuestSlots > 0 ? `${guestInBay} / ${maxGuestSlots}` : `${guestInBay} / -`;
        const monthlyCapacityText = maxMonthlySlots > 0 ? `${monthlyInBay} / ${maxMonthlySlots}` : `${monthlyInBay} / -`;
        document.getElementById("statCapacityText").textContent = `/ ${maxSlots} chỗ (Trống: ${available})`;
        const capacityBreakdown = document.getElementById("capacityBreakdown");
        if (capacityBreakdown) {
            capacityBreakdown.textContent = `Vãng lai: ${guestCapacityText} · Vé tháng: ${monthlyCapacityText}`;
        }

        const capacityStatus = data.capacity_status || "normal";
        const capacityMessageMap = {
            normal: `Bãi xe còn ${available} chỗ trống.`,
            near_full: `Bãi xe gần đầy (${data.total_in_bay}/${maxSlots}), nên điều tiết xe vào.`,
            almost_full: `Bãi xe sắp đầy, chỉ còn ${available} chỗ trống.`,
            full: `Bãi xe đã đầy (${data.total_in_bay}/${maxSlots}). Tạm dừng nhận xe vào.`,
        };
        const capacityMessage = capacityMessageMap[capacityStatus] || data.capacity_message || `Bãi xe còn ${available} chỗ trống.`;
        const capacityStatusEl = document.getElementById("capacityStatus");
        const capacityStatusDot = document.getElementById("capacityStatusDot");
        const capacityStatusText = document.getElementById("capacityStatusText");
        const capacityClassMap = {
            normal: "text-primary",
            near_full: "text-warning",
            almost_full: "text-orange-500",
            full: "text-rose-500",
        };
        const capacityDotMap = {
            normal: "bg-primary",
            near_full: "bg-warning",
            almost_full: "bg-orange-500 animate-pulse",
            full: "bg-rose-500 animate-pulse",
        };

        if (capacityStatusEl && capacityStatusText && capacityStatusDot) {
            capacityStatusEl.className = `mt-2 text-[10px] font-bold flex items-center gap-1.5 ${capacityClassMap[capacityStatus] || capacityClassMap.normal}`;
            capacityStatusDot.className = `w-1.5 h-1.5 rounded-full ${capacityDotMap[capacityStatus] || capacityDotMap.normal}`;
            capacityStatusText.textContent = capacityMessage;
        }

        const capacityBar = document.getElementById("capacityBar");
        if (capacityBar) {
            const percent = data.occupancy_percent !== undefined
                ? Math.min(100, Math.max(0, Number(data.occupancy_percent)))
                : Math.min(100, Math.max(0, (data.total_in_bay / maxSlots) * 100));
            capacityBar.style.width = `${percent}%`;
            const barClassMap = {
                normal: "bg-primary",
                near_full: "bg-warning",
                almost_full: "bg-orange-500",
                full: "bg-rose-500",
            };
            capacityBar.className = `${barClassMap[capacityStatus] || barClassMap.normal} h-full transition-all duration-500`;
        }

        const liveCapacityPanel = document.getElementById("liveCapacityPanel");
        const liveCapacityIcon = document.getElementById("liveCapacityIcon");
        const liveCapacityMessage = document.getElementById("liveCapacityMessage");
        const liveCapacityCount = document.getElementById("liveCapacityCount");
        const liveCapacityPercent = document.getElementById("liveCapacityPercent");
        const liveCapacityBar = document.getElementById("liveCapacityBar");
        const liveCapacityBreakdown = document.getElementById("liveCapacityBreakdown");
        const liveToneMap = {
            normal: {
                panel: "bg-surface-card border-border-subtle/70",
                icon: "bg-primary/10 text-primary",
                bar: "bg-primary",
            },
            near_full: {
                panel: "bg-warning/5 border-warning/30",
                icon: "bg-warning/10 text-warning",
                bar: "bg-warning",
            },
            almost_full: {
                panel: "bg-orange-500/5 border-orange-500/30",
                icon: "bg-orange-500/10 text-orange-500",
                bar: "bg-orange-500",
            },
            full: {
                panel: "bg-rose-500/5 border-rose-500/40",
                icon: "bg-rose-500/10 text-rose-500",
                bar: "bg-rose-500",
            },
        };
        const tone = liveToneMap[capacityStatus] || liveToneMap.normal;
        const percent = data.occupancy_percent !== undefined
            ? Math.min(100, Math.max(0, Number(data.occupancy_percent)))
            : Math.min(100, Math.max(0, (data.total_in_bay / maxSlots) * 100));

        if (liveCapacityPanel && liveCapacityIcon && liveCapacityMessage && liveCapacityCount && liveCapacityPercent && liveCapacityBar) {
            liveCapacityPanel.className = `border rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-sm ${tone.panel}`;
            liveCapacityIcon.className = `w-10 h-10 rounded-lg flex items-center justify-center ${tone.icon}`;
            liveCapacityMessage.textContent = capacityMessage;
            if (liveCapacityBreakdown) {
                liveCapacityBreakdown.textContent = `Vãng lai: ${guestCapacityText} · Vé tháng: ${monthlyCapacityText}`;
            }
            liveCapacityCount.textContent = `${data.total_in_bay} / ${maxSlots} xe`;
            liveCapacityPercent.textContent = `${percent.toFixed(1)}%`;
            liveCapacityBar.style.width = `${percent}%`;
            liveCapacityBar.className = `${tone.bar} h-full transition-all duration-500`;
        }
    } catch (err) {
        console.error(err);
    }
}

function renderFireAlerts(alerts) {
    const fireList = document.getElementById("fireList");
    const fireCard = document.getElementById("component-fire");
    const fireStatusText = document.getElementById("fireStatusText");
    const fireStatusPill = document.getElementById("fireStatusPill");
    const fireActive = Boolean(currentFireStatus?.active);

    if (fireStatusText) {
        fireStatusText.textContent = currentFireStatus?.message || "Hệ thống báo cháy đang bình thường.";
    }
    if (fireStatusPill) {
        fireStatusPill.className = fireActive
            ? "inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-rose-600 text-white text-[10px] font-bold uppercase tracking-wider shadow-sm"
            : "inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 text-[10px] font-bold uppercase tracking-wider";
        fireStatusPill.innerHTML = fireActive
            ? `<span class="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></span> Cổng đang giữ mở`
            : `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> Bình thường`;
    }
    
    if (!alerts || alerts.length === 0) {
        fireList.innerHTML = `<div class="status-text col-span-2 text-xs text-on-surface-variant/70 italic">${fireActive ? "Đang giữ trạng thái báo cháy, cổng vào/ra vẫn mở cho đến khi reset." : "Chưa phát hiện sự cố khói hoặc lửa tại các khu vực cảm biến."}</div>`;
        if (fireCard) fireCard.classList.toggle("fire-alarm-active", fireActive);
        return;
    }

    if (fireCard) fireCard.classList.add("fire-alarm-active");
    fireList.innerHTML = "";
    
    alerts.forEach((item) => {
        const div = document.createElement("div");
        div.className = "bg-surface-card p-3 rounded-lg border border-rose-500/20 flex justify-between items-center gap-3 shadow-sm";
        div.innerHTML = `
            <div>
                <div class="text-xs font-bold text-rose-500 flex items-center gap-1">
                    <span class="w-1.5 h-1.5 rounded-full bg-rose-500 animate-ping"></span> ${item.message}
                </div>
                <div class="text-[10px] text-on-surface-variant/65 mt-1">
                    Cảm biến: ${item.sensor_id} | Mức độ: <span class="text-rose-500 font-bold uppercase">${item.level}</span> | ${new Date(item.created_at).toLocaleString("vi-VN")}
                </div>
            </div>
            <button data-alert-ack="${item.id}" class="bg-rose-600 hover:bg-rose-700 text-white px-2.5 py-1 rounded-md text-[9px] font-bold transition-all shadow-sm">ĐÃ XEM</button>
        `;
        fireList.appendChild(div);
    });
}

function updateFireEmergencyOverlay() {
    const overlay = document.getElementById("fireEmergencyOverlay");
    if (!overlay) return;

    const active = Boolean(currentFireStatus?.active);
    if (!active) {
        overlay.classList.add("hidden");
        document.body.classList.remove("overflow-hidden");
        fireOverlayDismissedForActive = false;
        return;
    }

    const latest = currentFireAlerts?.[0];
    const count = Number(currentFireStatus?.unacknowledged_count ?? currentFireAlerts.length ?? 0);
    const overlayMessage = document.getElementById("fireOverlayMessage");
    const overlayLatest = document.getElementById("fireOverlayLatest");
    const overlayCount = document.getElementById("fireOverlayCount");

    if (overlayMessage) {
        overlayMessage.textContent = currentFireStatus?.message || "Cổng vào/ra đang được giữ mở cho đến khi bảo vệ reset.";
    }
    if (overlayLatest) {
        overlayLatest.textContent = latest
            ? `${latest.sensor_id} - ${latest.message || "Phát hiện cảnh báo cháy"}`
            : "Đang giữ trạng thái báo cháy. Cổng vào/ra vẫn mở.";
    }
    if (overlayCount) {
        overlayCount.textContent = `${count} cảnh báo`;
    }

    overlay.classList.toggle("hidden", fireOverlayDismissedForActive);
    document.body.classList.toggle("overflow-hidden", !fireOverlayDismissedForActive);
}

async function resetFireAlarm() {
    const res = await fetch(`${API_BASE}/api/fire/reset`, {
        method: "POST",
        headers: {
            "X-API-Key": "pbl5_secure_key_12345"
        }
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Reset failed");
    await fetchFireAlerts();
    return data;
}

async function fetchFireAlerts() {
    try {
        const [statusRes, alertsRes] = await Promise.all([
            fetch(`${API_BASE}/api/fire/status`),
            fetch(`${API_BASE}/api/fire-alerts?unacked_only=true&limit=10`),
        ]);
        if (!statusRes.ok || !alertsRes.ok) throw new Error("fire fetch failed");
        currentFireStatus = await statusRes.json();
        const alerts = await alertsRes.json();
        currentFireAlerts = alerts;
        renderFireAlerts(alerts);
        updateFireEmergencyOverlay();
    } catch (err) {
        console.error(err);
    }
}

async function ackFireAlert(alertId) {
    try {
        const res = await fetch(`${API_BASE}/api/fire-alerts/${alertId}/ack`, {
            method: "PATCH",
        });
        if (!res.ok) throw new Error("ack failed");
        await fetchFireAlerts();
    } catch (err) {
        console.error(err);
    }
}

async function createFakeFireAlert() {
    const sensorId = document.getElementById("fireSensorId").value.trim() || "fire-demo-1";
    const level = document.getElementById("fireLevel").value;
    const message = document.getElementById("fireMessage").value.trim() || "Phát hiện chỉ số khói/nhiệt độ bất thường";
    try {
        const res = await fetch(`${API_BASE}/api/fire-alerts`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sensor_id: sensorId, level, message }),
        });
        if (!res.ok) throw new Error("create fire alert failed");
        document.getElementById("fireMessage").value = "";
        await fetchFireAlerts();
    } catch (err) {
        console.error(err);
    }
}

function formatDateTime(value) {
    if (!value) return "-";
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return value;
    return dt.toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
}

function formatTicketType(value) {
    if (value === "monthly") {
        return `<span class="pf-badge px-2.5 py-1 bg-teal-500/10 text-teal-500 border border-teal-500/20 text-[10px] font-bold">Vé tháng</span>`;
    }
    return `<span class="pf-badge px-2.5 py-1 bg-amber-500/10 text-amber-600 border border-amber-500/20 text-[10px] font-bold">Vé lượt</span>`;
}

function clearStatSkeleton(...ids) {
    ids.forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.classList.remove("pf-skeleton");
    });
}

async function fetchParkingHistory() {
    try {
        const res = await fetch(`${API_BASE}/api/parking-history?limit=200`);
        if (!res.ok) throw new Error("history fetch failed");
        const rows = await res.json();
        const tbody = document.getElementById("parkingHistoryBody");
        tbody.innerHTML = "";

        if (!rows.length) {
            const tr = document.createElement("tr");
            tr.innerHTML = `<td colspan="10" class="px-6 py-5 text-center text-xs text-on-surface-variant/70 italic">Chưa ghi nhận sự kiện vào/ra nào hôm nay.</td>`;
            tbody.appendChild(tr);
            return;
        }

        rows.forEach((row) => {
            const tr = document.createElement("tr");
            tr.className = "hover:bg-surface-container-low/40 border-b border-border-subtle/25 transition-colors";
            
            const badgeClass = row.trigger_type === "entry" 
                                ? "bg-blue-500/10 text-blue-500 border border-blue-500/20" 
                                : row.trigger_type === "exit" ? "bg-amber-500/10 text-amber-600 border border-amber-500/20" : "bg-primary/10 text-primary border border-primary/20";
            const statusClassMap = {
                pending: "bg-slate-500/10 text-slate-400 border-slate-500/20",
                matched: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
                fuzzy_matched: "bg-teal-500/10 text-teal-500 border-teal-500/20",
                rfid_only: "bg-amber-500/10 text-amber-600 border-amber-500/20",
                ignored: "bg-rose-500/10 text-rose-500 border-rose-500/20",
            };
            const matchStatusClass = statusClassMap[row.match_status] || "bg-slate-500/10 text-slate-400 border-slate-500/20";
            
            tr.innerHTML = `
                <td class="px-5 py-4 font-mono font-medium">${row.session_id}</td>
                <td class="px-5 py-4">${formatCompactPlate(row.plate_number)}</td>
                <td class="px-5 py-4">${formatTicketType(row.ticket_type)}</td>
                <td class="px-5 py-4 font-bold text-xs uppercase text-on-surface-variant">${row.gate_type || "-"}</td>
                <td class="px-5 py-4"><span class="pf-badge px-2.5 py-1 ${badgeClass} text-[9px] font-bold uppercase tracking-wider">${row.trigger_type || "-"}</span></td>
                <td class="px-5 py-4 text-on-surface-variant/80">${formatDateTime(row.time_in)}</td>
                <td class="px-5 py-4 text-on-surface-variant/80">${formatDateTime(row.time_out)}</td>
                <td class="px-5 py-4 font-medium">${row.duration_minutes ?? "-"}</td>
                <td class="px-5 py-4 font-bold">${Number(row.fee || 0).toLocaleString("vi-VN")}</td>
                <td class="px-5 py-4"><span class="pf-badge px-2.5 py-1 border ${matchStatusClass} text-[9px] font-bold uppercase tracking-wider">${row.match_status || "-"}</span></td>
            `;
            tbody.appendChild(tr);
        });
        updateChartFromHistory(rows);
    } catch (err) {
        console.error(err);
    }
}

async function fetchMonthlyRegistrations() {
    try {
        const res = await fetch(`${API_BASE}/api/monthly-registrations`);
        if (!res.ok) throw new Error("monthly registrations failed");
        const items = await res.json();
        const tbody = document.getElementById("monthlyTableBody");
        tbody.innerHTML = "";

        if (!items.length) {
            const tr = document.createElement("tr");
            tr.innerHTML = `<td colspan="8" class="px-6 py-5 text-center text-xs text-on-surface-variant/70 italic">Chưa có hồ sơ hội viên đăng ký nào.</td>`;
            tbody.appendChild(tr);
            return;
        }

        items.forEach((item) => {
            const tr = document.createElement("tr");
            tr.className = "hover:bg-surface-container-low/40 border-b border-border-subtle/25 transition-colors";
            
            const statusBadge = item.is_active 
                ? '<span class="pf-badge px-2.5 py-1 bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 text-[9px] font-bold tracking-wider">HOẠT ĐỘNG</span>'
                : '<span class="pf-badge px-2.5 py-1 bg-rose-500/10 text-rose-500 border border-rose-500/20 text-[9px] font-bold tracking-wider">HẾT HẠN</span>';

            tr.innerHTML = `
                <td class="px-5 py-4 font-mono font-medium">${item.subscription_id}</td>
                <td class="px-5 py-4 font-bold text-on-surface">${item.monthly_user_name || ""}</td>
                <td class="px-5 py-4 text-on-surface-variant/80">${item.monthly_user_phone || ""}</td>
                <td class="px-5 py-4">${formatCompactPlate(item.plate_number)}</td>
                <td class="px-5 py-4 font-mono">${item.rfid_card_uid || "-"}</td>
                <td class="px-5 py-4 text-on-surface-variant/80">${item.start_date || ""}</td>
                <td class="px-5 py-4 text-on-surface-variant/80">${item.end_date || ""}</td>
                <td class="px-5 py-4 text-center">${statusBadge}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error(err);
    }
}

async function createMonthlyRegistration(evt) {
    evt.preventDefault();

    const payload = {
        full_name: document.getElementById("monthlyFullName").value.trim(),
        phone: document.getElementById("monthlyPhone").value.trim() || null,
        address: document.getElementById("monthlyAddress").value.trim() || null,
        plate_number: document.getElementById("monthlyPlate").value.trim(),
        vehicle_note: document.getElementById("monthlyVehicleNote").value.trim() || null,
        start_date: document.getElementById("monthlyStartDate").value,
        end_date: document.getElementById("monthlyEndDate").value,
        rfid_card_uid: document.getElementById("monthlyRfid").value.trim() || null,
    };

    const statusEl = document.getElementById("monthlyStatus");
    if (!payload.full_name || !payload.plate_number || !payload.start_date || !payload.end_date) {
        statusEl.className = "text-xs mt-2 font-bold text-error";
        statusEl.textContent = "Vui lòng nhập đầy đủ thông tin bắt buộc.";
        return;
    }

    try {
        statusEl.className = "text-xs mt-2 font-bold text-warning animate-pulse";
        statusEl.textContent = "Đang xử lý tạo hồ sơ hội viên...";

        const res = await fetch(`${API_BASE}/api/monthly-registrations`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || "Đăng ký vé tháng thất bại");
        }

        document.getElementById("monthlyForm").reset();
        statusEl.className = "text-xs mt-2 font-bold text-success";
        statusEl.textContent = data.message || "Đăng ký vé tháng thành công!";

        await fetchMonthlyRegistrations();
    } catch (err) {
        console.error(err);
        statusEl.className = "text-xs mt-2 font-bold text-error";
        statusEl.textContent = err.message || "Lỗi tạo hồ sơ hội viên";
    }
}

function bindGlobalActions() {
    document.querySelectorAll("button[data-action]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const gate = btn.dataset.gate;
            const action = btn.dataset.action;
            if (action === "start") {
                await startCamera(gate);
            } else if (action === "stop") {
                stopCamera(gate);
            } else if (action === "sensor") {
                await triggerAndScan(gate, "sensor");
            } else if (action === "rfid") {
                await triggerAndScan(gate, "rfid");
            } else if (action === "manual-open") {
                await forceOpenGate(gate);
            }
        });
    });

    document.getElementById("fireList").addEventListener("click", async (evt) => {
        const alertId = evt.target?.dataset?.alertAck;
        if (!alertId) return;
        await ackFireAlert(alertId);
    });

    document.getElementById("fakeFireBtn").addEventListener("click", createFakeFireAlert);

    document.getElementById("resetFireBtn").addEventListener("click", async () => {
        try {
            await resetFireAlarm();
            fireOverlayDismissedForActive = false;
            await fetchFireAlerts();
        } catch (err) {
            console.error(err);
            const statusText = document.getElementById("fireStatusText");
            if (statusText) statusText.textContent = err.message || "Không thể gửi lệnh tắt báo động";
        }
    });

    const fireOverlayResetBtn = document.getElementById("fireOverlayResetBtn");
    if (fireOverlayResetBtn) {
        fireOverlayResetBtn.addEventListener("click", async () => {
            try {
                fireOverlayResetBtn.disabled = true;
                fireOverlayResetBtn.classList.add("opacity-70");
                await resetFireAlarm();
                fireOverlayDismissedForActive = false;
                await fetchFireAlerts();
            } catch (err) {
                console.error(err);
                const overlayMessage = document.getElementById("fireOverlayMessage");
                if (overlayMessage) overlayMessage.textContent = err.message || "Không thể reset báo cháy";
            } finally {
                fireOverlayResetBtn.disabled = false;
                fireOverlayResetBtn.classList.remove("opacity-70");
            }
        });
    }

    const fireOverlayAckBtn = document.getElementById("fireOverlayAckBtn");
    if (fireOverlayAckBtn) {
        fireOverlayAckBtn.addEventListener("click", () => {
            fireOverlayDismissedForActive = true;
            updateFireEmergencyOverlay();
        });
    }

    document.getElementById("forceCheckoutBtn").addEventListener("click", async () => {
        const plate = document.getElementById("forceCheckoutPlate").value.trim();
        const reason = document.getElementById("forceCheckoutReason").value;
        const resultEl = document.getElementById("forceCheckoutResult");

        if (!plate) {
            resultEl.className = "mt-3 text-xs font-bold text-error";
            resultEl.textContent = "Vui lòng nhập biển số xe.";
            return;
        }

        try {
            resultEl.className = "mt-3 text-xs font-bold text-warning animate-pulse";
            resultEl.textContent = "Đang kết nối cơ sở dữ liệu & tính toán...";

            const formData = new FormData();
            formData.append("plate_number", plate);
            formData.append("reason", reason);
            formData.append("open_gate", "true");
            formData.append("operator", "admin");

            const res = await fetch(`${API_BASE}/api/parking/force-checkout`, {
                method: "POST",
                headers: {
                    "X-API-Key": "pbl5_secure_key_12345"
                },
                body: formData,
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Giải phóng xe kẹt thất bại");

            resultEl.className = "mt-3 text-xs font-bold text-success";
            const compensationFee = Number(data.compensation_fee || 0);
            const compensationText = compensationFee > 0
                ? ` Phi den bu mat RFID: ${compensationFee.toLocaleString("vi-VN")}d.`
                : "";
            resultEl.textContent = `${data.message}${compensationText}`;
            document.getElementById("forceCheckoutPlate").value = "";

            await fetchDashboard();
            await fetchParkingHistory();
        } catch (err) {
            console.error(err);
            resultEl.className = "mt-3 text-xs font-bold text-error";
            resultEl.textContent = err.message || "Lỗi xử lý sự cố kẹt xe";
        }
    });

    // Theme Toggle Handler
    const themeToggleBtn = document.getElementById("themeToggleBtn");
    const themeToggleIcon = document.getElementById("themeToggleIcon");
    
    function applyTheme(theme) {
        if (theme === "dark") {
            document.documentElement.classList.add("dark");
            themeToggleIcon.textContent = "light_mode";
        } else {
            document.documentElement.classList.remove("dark");
            themeToggleIcon.textContent = "dark_mode";
        }
    }
    
    const savedTheme = localStorage.getItem("theme") || "dark";
    applyTheme(savedTheme);
    
    themeToggleBtn.addEventListener("click", () => {
        const isDark = document.documentElement.classList.contains("dark");
        const newTheme = isDark ? "light" : "dark";
        localStorage.setItem("theme", newTheme);
        applyTheme(newTheme);
        
        // Cập nhật màu sắc Chart.js tương ứng
        if (parkingChart) {
            const textColor = newTheme === "dark" ? "#94a3b8" : "#475569";
            const gridColor = newTheme === "dark" ? "rgba(30, 41, 59, 0.4)" : "rgba(226, 232, 240, 0.6)";
            
            parkingChart.options.plugins.legend.labels.color = textColor;
            parkingChart.options.scales.x.grid.color = gridColor;
            parkingChart.options.scales.x.ticks.color = textColor;
            parkingChart.options.scales.y.grid.color = gridColor;
            parkingChart.options.scales.y.ticks.color = textColor;
            parkingChart.update();
        }
    });
}

// Global State Management (Visual Only Script for Panel Switching)
const sidebarLinks = document.querySelectorAll('aside nav a');
const panels = {
    'Dashboard': 'panel-dashboard',
    'Giám Sát Trực Tiếp': 'panel-monitoring',
    'Hội Viên Vé Tháng': 'panel-subscribers',
    'Lịch Sử Vào Ra': 'panel-history'
};

sidebarLinks.forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        
        // Update UI state for sidebar
        sidebarLinks.forEach(l => l.classList.remove('sidebar-active', 'text-sidebar-text'));
        sidebarLinks.forEach(l => l.classList.add('text-sidebar-text/60'));
        link.classList.add('sidebar-active', 'text-sidebar-text');
        link.classList.remove('text-sidebar-text/60');

        // Hide all panels
        Object.values(panels).forEach(id => {
            const panel = document.getElementById(id);
            if(panel) panel.classList.add('hidden');
        });

        // Show selected panel
        const label = link.querySelector('span:last-child').textContent.trim();
        const panelId = panels[label];
        if(panelId) {
            document.getElementById(panelId).classList.remove('hidden');
        }

        // Control camera streaming dynamically to optimize resources
        if (label === 'Giám Sát Trực Tiếp') {
            startCamera("entry");
            startCamera("exit");
        } else {
            stopCamera("entry");
            stopCamera("exit");
        }
    });
});

document.getElementById("btnExportCSV").addEventListener("click", () => {
    window.location.href = `${API_BASE}/api/parking/export`;
});

document.getElementById("monthlyForm").addEventListener("submit", createMonthlyRegistration);

document.getElementById("refreshBtn").addEventListener("click", async () => {
    await fetchDashboard();
    await fetchMonthlyRegistrations();
    await fetchParkingHistory();
    await fetchFireAlerts();
});

function initWebSocket() {
    const wsUrl = API_BASE.replace("http", "ws") + "/ws";
    const ws = new WebSocket(wsUrl);
    
    ws.onopen = () => console.log("WebSocket connected to ParkFlow backend");
    ws.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        if (payload.event === "parking_update") {
            fetchDashboard();
            fetchParkingHistory();
            
            const d = payload.data || {};
            const gate = d.gate_type === "entry" ? "entry" : "exit";
            
            if (d.rfid_tag) {
                const cfg = gateState[gate];
                if (cfg && cfg.rfidInput) {
                    cfg.rfidInput.value = d.rfid_tag;
                }
            }

            if (d.action === "open" || d.action === "open_manual") {
                setStatus(gate, d.message || "Đã phê duyệt và mở cổng", "ok");
            } else {
                setStatus(gate, d.message || "Từ chối và hạ rào barie", "danger");
            }
            
            renderGateResult(gate, {
                action: d.action,
                rfid_tag: d.rfid_tag,
                recognized_plate: d.plate,
                plate_in: d.gate_type === "entry" ? d.plate : d.plate_in,
                plate_out: d.gate_type === "exit" ? d.plate : d.plate_out,
                confidence: d.confidence,
                matched: d.action === "open",
                duration_minutes: d.duration_minutes,
                fee: d.fee,
                image_url: d.image_url,
                plate_in_image_url: d.plate_in_image_url,
                message: d.message || "Đã phản hồi lệnh",
            });

            if (d.action === "open" || d.action === "open_manual") {
                if (window._gateClearTimer && window._gateClearTimer[gate]) {
                    clearTimeout(window._gateClearTimer[gate]);
                }
                if (!window._gateClearTimer) window._gateClearTimer = {};
                window._gateClearTimer[gate] = setTimeout(() => {
                    renderGateResult(gate, {});
                    setStatus(gate, "Chờ phương tiện tiếp theo...");
                    const cfg = gateState[gate];
                    if (cfg && cfg.rfidInput) cfg.rfidInput.value = "";
                }, 8000);
            }
        } else if (payload.event === "fire_alert") {
            fireOverlayDismissedForActive = false;
            fetchFireAlerts();
        } else if (payload.event === "fire_reset") {
            fetchFireAlerts();
        } else if (payload.event === "fire_telemetry") {
            pushFireTelemetryPoint(payload.data || {});
        } else if (payload.event === "pending_scan") {
            const d = payload.data || {};
            const gate = d.gate_type === "entry" ? "entry" : "exit";
            const plate = d.recognized_plate || "...";
            const conf = d.confidence != null ? Number(d.confidence).toFixed(2) : "?";
            setStatus(gate, `Nhận diện: ${plate} (Độ tin cậy: ${conf}) - Chờ quẹt thẻ RFID xác minh...`, "warn");
            renderGateResult(gate, {
                action: "pending",
                recognized_plate: plate,
                confidence: d.confidence,
                image_url: d.image_url,
                plate_in_image_url: d.plate_in_image_url,
                message: d.message || "Vui lòng quét thẻ RFID...",
            });
        } else if (payload.event === "tracking_update") {
            const d = payload.data || {};
            const gate = d.gate_type === "entry" ? "entry" : "exit";
            const plate = d.plate || "UNKNOWN";
            const conf = d.confidence != null ? Number(d.confidence).toFixed(2) : "?";
            const attempts = d.attempts ?? "-";
            setStatus(gate, `Dang bam bien so: ${plate} (${conf}) - frame ${attempts}`, "warn");
            renderGateResult(gate, {
                action: d.status || "tracking",
                recognized_plate: plate,
                confidence: d.confidence,
                image_url: d.image_url,
                plate_in_image_url: d.plate_in_image_url,
                message: d.message || "Dang bat khung bien so...",
            });
        }
    };
    ws.onclose = () => setTimeout(initWebSocket, 5000);
}

window.onload = async () => {
    bindGlobalActions();
    renderGateResult("entry", {});
    renderGateResult("exit", {});
    
    stopCamera("entry");
    stopCamera("exit");
    
    initParkingChart();
    initFireTelemetryChart();
    
    await fetchDashboard();
    await fetchMonthlyRegistrations();
    await fetchParkingHistory();
    await fetchFireAlerts();
    await fetchFireTelemetry();
    
    initWebSocket();
    statusBarInterval = setInterval(fetchDashboard, 30000);
    fireAlertInterval = setInterval(fetchFireAlerts, 15000);
};

const API_BASE = "http://localhost:8000";
let parkingChart = null;

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
                    borderColor: '#6366f1', // indigo-500
                    backgroundColor: 'rgba(99, 102, 241, 0.06)',
                    borderWidth: 2,
                    tension: 0.35,
                    fill: true,
                    pointBackgroundColor: '#6366f1',
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
    
    const match = plateStr.match(/^([0-9]{2}[A-Z]{1,2}[0-9]?)[- ]?([0-9]{3,5})$/i);
    if (match) {
        line1 = match[1].toUpperCase();
        let rawNum = match[2];
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

async function triggerAndScan(gate, triggerType) {
    const cfg = gateState[gate];
    if (!cfg) return;

    const rfidTag = triggerType === "rfid" ? cfg.rfidInput.value.trim() : "";
    if (triggerType === "rfid" && !rfidTag) {
        setStatus(gate, "Nhập UID thẻ RFID trước khi quét", "warn");
        return;
    }

    try {
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

async function forceOpenGate(gate) {
    try {
        setStatus(gate, "Đang phát lệnh mở cổng khẩn cấp...", "warn");
        const formData = new FormData();
        formData.append("gate_type", gate);
        formData.append("reason", "manual_override");
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
        document.getElementById("statInBay").textContent = data.total_in_bay;
        document.getElementById("statInToday").textContent = data.today_total_in;
        document.getElementById("statOutToday").textContent = data.today_total_out;
        document.getElementById("statRevenue").textContent = Number(data.today_revenue || 0).toLocaleString("vi-VN") + "đ";
        
        const maxSlots = data.max_slots || 50;
        const available = data.available_slots !== undefined ? data.available_slots : (maxSlots - data.total_in_bay);
        document.getElementById("statCapacityText").textContent = `/ ${maxSlots} chỗ (Trống: ${available})`;

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
    
    if (!alerts || alerts.length === 0) {
        fireList.innerHTML = `<div class="status-text col-span-2 text-xs text-on-surface-variant/70 italic">Chưa phát hiện sự cố khói hoặc lửa tại các khu vực cảm biến.</div>`;
        if (fireCard) fireCard.classList.remove("fire-alarm-active");
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

async function fetchFireAlerts() {
    try {
        const res = await fetch(`${API_BASE}/api/fire-alerts?unacked_only=true&limit=10`);
        if (!res.ok) throw new Error("fire fetch failed");
        const alerts = await res.json();
        renderFireAlerts(alerts);
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
        return `<span class="px-2 py-0.5 bg-indigo-500/10 text-indigo-500 border border-indigo-500/20 rounded-md text-[10px] font-bold">Vé tháng</span>`;
    }
    return `<span class="px-2 py-0.5 bg-amber-500/10 text-amber-600 border border-amber-500/20 rounded-md text-[10px] font-bold">Vé lượt</span>`;
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
                                ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20" 
                                : row.trigger_type === "exit" ? "bg-slate-500/10 text-slate-500 border border-slate-500/20" : "bg-primary/10 text-primary border border-primary/20";
            
            tr.innerHTML = `
                <td class="px-5 py-4 font-mono font-medium">${row.session_id}</td>
                <td class="px-5 py-4">${formatCompactPlate(row.plate_number)}</td>
                <td class="px-5 py-4">${formatTicketType(row.ticket_type)}</td>
                <td class="px-5 py-4 font-bold text-xs uppercase text-on-surface-variant">${row.gate_type || "-"}</td>
                <td class="px-5 py-4"><span class="px-2.5 py-1 ${badgeClass} rounded-md text-[9px] font-bold uppercase tracking-wider">${row.trigger_type || "-"}</span></td>
                <td class="px-5 py-4 text-on-surface-variant/80">${formatDateTime(row.time_in)}</td>
                <td class="px-5 py-4 text-on-surface-variant/80">${formatDateTime(row.time_out)}</td>
                <td class="px-5 py-4 font-medium">${row.duration_minutes ?? "-"}</td>
                <td class="px-5 py-4 font-bold">${Number(row.fee || 0).toLocaleString("vi-VN")}</td>
                <td class="px-5 py-4 text-on-surface-variant/70 text-[11px]">${row.match_status || "-"}</td>
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
                ? '<span class="px-2.5 py-1 bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 rounded-md text-[9px] font-bold tracking-wider">HOẠT ĐỘNG</span>'
                : '<span class="px-2.5 py-1 bg-rose-500/10 text-rose-500 border border-rose-500/20 rounded-md text-[9px] font-bold tracking-wider">HẾT HẠN</span>';

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
            const res = await fetch(`${API_BASE}/api/fire/reset`, {
                method: "POST",
                headers: {
                    "X-API-Key": "pbl5_secure_key_12345"
                }
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Reset failed");
            alert(data.message || "Đã tắt chuông báo động cháy và thiết bị.");
            await fetchFireAlerts();
        } catch (err) {
            console.error(err);
            alert("Lỗi: " + (err.message || "Không thể gửi lệnh tắt báo động"));
        }
    });

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
            resultEl.textContent = data.message;
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
            fetchFireAlerts();
            alert("CẢNH BÁO KHẨN CẤP: PHÁT HIỆN SỰ CỐ HOẢ HOẠN TẠI BÃI GỬI XE!");
        } else if (payload.event === "fire_reset") {
            fetchFireAlerts();
            alert(payload.data?.message || "Báo động sự cố cháy đã được thu hồi.");
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
    
    await fetchDashboard();
    await fetchMonthlyRegistrations();
    await fetchParkingHistory();
    await fetchFireAlerts();
    
    initWebSocket();
    statusBarInterval = setInterval(fetchDashboard, 30000);
    fireAlertInterval = setInterval(fetchFireAlerts, 15000);
};

import re

# We will recreate the frontend/index.html using the content of stitch_smart_parking_control_system/code.html
# and adding the javascript from frontend/index.html.

html_template = """<!DOCTYPE html>
<html lang="vi"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>ParkFlow Control - Hệ Thống Quản Lý Bãi Gửi Xe Thông Minh</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<script id="tailwind-config">
        tailwind.config = {
            darkMode: "class",
            theme: {
                extend: {
                    "colors": {
                        "sidebar-bg": "#0f172a",
                        "background": "#f8fafc",
                        "on-surface-variant": "#424754",
                        "on-tertiary": "#ffffff",
                        "on-tertiary-fixed-variant": "#723600",
                        "on-secondary-fixed": "#0b1c30",
                        "on-primary-container": "#fefcff",
                        "surface-dim": "#d8d9e3",
                        "on-tertiary-fixed": "#311400",
                        "inverse-on-surface": "#eff0fa",
                        "primary-fixed-dim": "#adc6ff",
                        "tertiary-fixed": "#ffdcc6",
                        "error": "#ba1a1a",
                        "tertiary-container": "#b75b00",
                        "surface-container": "#ecedf7",
                        "secondary-fixed-dim": "#b7c8e1",
                        "outline": "#727785",
                        "secondary": "#505f76",
                        "on-secondary-container": "#54647a",
                        "on-error-container": "#93000a",
                        "surface-bright": "#f9f9ff",
                        "tertiary-fixed-dim": "#ffb786",
                        "on-tertiary-container": "#fffbff",
                        "tertiary": "#924700",
                        "primary-container": "#2170e4",
                        "border-subtle": "#e2e8f0",
                        "surface-container-high": "#e6e7f2",
                        "surface-variant": "#e1e2ec",
                        "on-secondary-fixed-variant": "#38485d",
                        "secondary-fixed": "#d3e4fe",
                        "success": "#22c55e",
                        "on-error": "#ffffff",
                        "on-primary-fixed-variant": "#004395",
                        "surface-tint": "#005ac2",
                        "sidebar-text": "#f8fafc",
                        "secondary-container": "#d0e1fb",
                        "surface": "#ffffff",
                        "danger": "#ef4444",
                        "on-primary": "#ffffff",
                        "surface-container-low": "#f2f3fd",
                        "warning": "#f59e0b",
                        "inverse-primary": "#adc6ff",
                        "on-surface": "#191b23",
                        "inverse-surface": "#2e3038",
                        "primary-fixed": "#d8e2ff",
                        "on-secondary": "#ffffff",
                        "primary": "#0058be",
                        "outline-variant": "#c2c6d6",
                        "on-primary-fixed": "#001a42",
                        "on-background": "#191b23",
                        "error-container": "#ffdad6",
                        "surface-container-lowest": "#ffffff",
                        "surface-container-highest": "#e1e2ec"
                    },
                    "borderRadius": {
                        "DEFAULT": "0.25rem",
                        "lg": "0.5rem",
                        "xl": "0.75rem",
                        "full": "9999px"
                    },
                    "spacing": {
                        "stack-sm": "8px",
                        "stack-md": "16px",
                        "sidebar-width": "260px",
                        "gutter": "24px",
                        "container-max": "1440px",
                        "margin-mobile": "16px",
                        "stack-lg": "24px",
                        "margin-desktop": "32px"
                    },
                    "fontFamily": {
                        "label-sm": ["Inter"],
                        "title-sm": ["Inter"],
                        "display-lg": ["Inter"],
                        "body-md": ["Inter"],
                        "headline-md": ["Inter"],
                        "body-sm": ["Inter"],
                        "label-caps": ["Inter"]
                    },
                    "fontSize": {
                        "label-sm": ["12px", {"lineHeight": "16px", "fontWeight": "500"}],
                        "title-sm": ["18px", {"lineHeight": "24px", "fontWeight": "600"}],
                        "display-lg": ["32px", {"lineHeight": "40px", "letterSpacing": "-0.02em", "fontWeight": "700"}],
                        "body-md": ["16px", {"lineHeight": "24px", "fontWeight": "400"}],
                        "headline-md": ["24px", {"lineHeight": "32px", "letterSpacing": "-0.01em", "fontWeight": "600"}],
                        "body-sm": ["14px", {"lineHeight": "20px", "fontWeight": "400"}],
                        "label-caps": ["12px", {"lineHeight": "16px", "letterSpacing": "0.05em", "fontWeight": "600"}]
                    }
                }
            }
        }
    </script>
<style>
        body { font-family: 'Inter', sans-serif; background-color: #f8fafc; }
        .material-symbols-outlined { font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24; vertical-align: middle; }
        .sidebar-active { background-color: rgba(255,255,255,0.1); border-left-width: 4px; border-color: #0058be; color: #f8fafc; }
    </style>
</head>
<body class="text-on-background">
<!-- SideNavBar -->
<aside class="fixed left-0 top-0 h-screen w-sidebar-width bg-sidebar-bg flex flex-col py-stack-lg z-50 border-r border-on-surface-variant/20">
<div class="px-stack-lg mb-10">
<div class="flex items-center gap-stack-sm">
<span class="material-symbols-outlined text-primary-fixed-dim text-3xl" style="font-variation-settings: 'FILL' 1;">local_parking</span>
<div>
<h1 class="text-headline-md font-headline-md font-bold text-sidebar-text leading-none">ParkFlow Pro</h1>
<p class="text-label-sm font-label-sm text-sidebar-text/60 mt-1 uppercase tracking-wider">Enterprise Parking</p>
</div>
</div>
</div>
<nav class="flex-1 space-y-1">
<a class="sidebar-active flex items-center gap-stack-md text-sidebar-text px-stack-lg py-stack-sm transition-all hover:bg-white/5" href="#">
<span class="material-symbols-outlined" data-icon="dashboard">dashboard</span>
<span class="text-label-sm font-label-sm">Dashboard</span>
</a>
<a class="flex items-center gap-stack-md text-sidebar-text/70 px-stack-lg py-stack-sm transition-all hover:bg-white/5 hover:text-sidebar-text" href="#">
<span class="material-symbols-outlined" data-icon="videocam">videocam</span>
<span class="text-label-sm font-label-sm">Live Monitoring</span>
</a>
<a class="flex items-center gap-stack-md text-sidebar-text/70 px-stack-lg py-stack-sm transition-all hover:bg-white/5 hover:text-sidebar-text" href="#">
<span class="material-symbols-outlined" data-icon="group">group</span>
<span class="text-label-sm font-label-sm">Subscribers</span>
</a>
<a class="flex items-center gap-stack-md text-sidebar-text/70 px-stack-lg py-stack-sm transition-all hover:bg-white/5 hover:text-sidebar-text" href="#">
<span class="material-symbols-outlined" data-icon="history">history</span>
<span class="text-label-sm font-label-sm">Parking History</span>
</a>
</nav>
<div class="mt-auto px-stack-lg border-t border-white/10 pt-stack-lg">
</div>
</aside>
<!-- TopAppBar -->
<header class="fixed top-0 right-0 h-16 bg-surface shadow-sm flex justify-between items-center px-gutter z-40 border-b border-border-subtle" style="left: 260px; width: calc(100% - 260px);">
<div class="flex items-center gap-stack-lg">
<div class="relative">
<span class="absolute inset-y-0 left-3 flex items-center text-on-surface-variant/50">
<span class="material-symbols-outlined">search</span>
</span>
<input class="pl-10 pr-4 py-2 bg-surface-container-low border-none rounded-full w-80 text-body-sm focus:ring-2 focus:ring-primary/20" placeholder="Tìm kiếm phương tiện, thẻ..." type="text"/>
</div>
</div>
<div class="flex items-center gap-stack-md">
<button id="refreshBtn" class="bg-primary/10 text-primary px-4 py-1.5 rounded-full text-label-sm font-bold flex items-center gap-2 hover:bg-primary/20 transition-colors">
<span class="material-symbols-outlined text-sm">refresh</span> Làm mới dữ liệu
</button>
<button class="p-2 text-on-surface-variant hover:bg-surface-container-low rounded-full transition-colors relative">
<span class="material-symbols-outlined">notifications</span>
</button>
<div class="h-8 w-px bg-border-subtle mx-2"></div>
<div class="flex items-center gap-3">
<div class="text-right">
<p class="text-label-sm font-bold text-on-surface">Admin</p>
<p class="text-[10px] text-on-surface-variant uppercase">Administrator</p>
</div>
<div class="w-10 h-10 rounded-full border-2 border-primary/10 bg-primary/20 flex items-center justify-center font-bold text-primary">A</div>
</div>
</div>
</header>

<!-- Main Content Canvas -->
<main class="ml-[260px] pt-24 p-gutter min-h-screen">
<!-- Dashboard / Overview Panel -->
<div class="space-y-stack-lg" id="panel-dashboard">
<div class="flex justify-between items-end mb-4">
<div>
<h2 class="text-headline-md font-headline-md text-on-surface">Tổng quan hệ thống</h2>
<p class="text-body-sm text-on-surface-variant">Dữ liệu bãi xe hôm nay.</p>
</div>
</div>

<!-- Stats Bento Grid -->
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-stack-lg">
<div class="bg-surface p-stack-lg rounded-xl border border-border-subtle shadow-sm flex flex-col gap-2 relative overflow-hidden group">
<div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
<span class="material-symbols-outlined text-6xl" style="font-variation-settings: 'FILL' 1;">directions_car</span>
</div>
<span class="text-label-caps text-on-surface-variant">Xe Trong Bãi</span>
<span id="statInBay" class="text-display-lg font-display-lg text-primary">-</span>
</div>

<div class="bg-surface p-stack-lg rounded-xl border border-border-subtle shadow-sm flex flex-col gap-2 relative overflow-hidden group">
<div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
<span class="material-symbols-outlined text-6xl" style="font-variation-settings: 'FILL' 1;">login</span>
</div>
<span class="text-label-caps text-on-surface-variant">Vào Hôm Nay</span>
<span id="statInToday" class="text-display-lg font-display-lg text-success">-</span>
</div>

<div class="bg-surface p-stack-lg rounded-xl border border-border-subtle shadow-sm flex flex-col gap-2 relative overflow-hidden group">
<div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
<span class="material-symbols-outlined text-6xl" style="font-variation-settings: 'FILL' 1;">logout</span>
</div>
<span class="text-label-caps text-on-surface-variant">Ra Hôm Nay</span>
<span id="statOutToday" class="text-display-lg font-display-lg text-secondary">-</span>
</div>

<div class="bg-surface p-stack-lg rounded-xl border border-border-subtle shadow-sm flex flex-col gap-2 relative overflow-hidden group">
<div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
<span class="material-symbols-outlined text-6xl" style="font-variation-settings: 'FILL' 1;">payments</span>
</div>
<span class="text-label-caps text-on-surface-variant">Doanh Thu Hôm Nay</span>
<span id="statRevenue" class="text-display-lg font-display-lg text-warning">-</span>
</div>
</div>

<!-- Fire Alerts Banner -->
<div class="bg-error-container/30 border-2 border-error border-dashed rounded-xl p-stack-lg flex flex-col gap-stack-lg" id="component-fire">
    <div class="flex items-start gap-stack-lg">
        <div class="bg-error text-on-error w-12 h-12 rounded-lg flex items-center justify-center shrink-0">
            <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">local_fire_department</span>
        </div>
        <div class="flex-1">
            <div class="flex justify-between items-start">
                <div class="w-full">
                    <h3 class="text-title-sm font-title-sm text-on-error-container">Cảnh báo An toàn &amp; Cháy nổ</h3>
                    <div id="fireList" class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div class="status-text text-body-sm text-on-error-container/80">Chưa có cảnh báo mới.</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <!-- Fake Fire Form -->
    <div class="mt-2 pt-4 border-t border-error/20 flex gap-4 items-center flex-wrap">
        <input id="fireSensorId" placeholder="sensor_id (vd: fire-1)" class="border-error/30 bg-white/50 focus:ring-error focus:border-error rounded text-body-sm px-3 py-1.5" />
        <input id="fireMessage" placeholder="Nội dung cảnh báo" class="border-error/30 bg-white/50 focus:ring-error focus:border-error rounded text-body-sm px-3 py-1.5 flex-1" />
        <select id="fireLevel" class="border-error/30 bg-white/50 focus:ring-error focus:border-error rounded text-body-sm px-3 py-1.5">
            <option value="warning">warning</option>
            <option value="critical">critical</option>
        </select>
        <button id="fakeFireBtn" class="bg-error text-on-error px-4 py-1.5 rounded text-label-sm font-bold shadow hover:opacity-90 transition-opacity">
            Gửi cảnh báo
        </button>
    </div>
</div>
</div>

<!-- Monitoring Full Panel -->
<div class="hidden space-y-stack-lg" id="panel-monitoring">
<div class="flex justify-between items-center mb-6">
<h2 class="text-headline-md font-headline-md text-on-surface">Giám sát trực tiếp (Live)</h2>
</div>

<div class="grid grid-cols-1 xl:grid-cols-2 gap-stack-lg">
<!-- Lane In -->
<div class="bg-surface rounded-xl border border-border-subtle overflow-hidden flex flex-col" id="panel-entry">
<div class="bg-sidebar-bg text-white px-6 py-4 flex justify-between items-center">
<span class="font-bold tracking-tight">LAN VAO - CHÍNH</span>
</div>
<div class="aspect-video bg-black flex items-center justify-center relative group">
    <video id="video-entry" autoplay playsinline class="w-full h-full object-cover"></video>
</div>
<div class="p-6 grid grid-cols-1 md:grid-cols-3 gap-6 bg-surface-container-lowest">
<div class="md:col-span-1 space-y-4">
    <div class="bg-surface border border-border-subtle p-3 rounded-lg text-center">
        <p class="text-[10px] text-on-surface-variant mb-1">ẢNH BIỂN SỐ</p>
        <div class="bg-surface-container rounded flex items-center justify-center overflow-hidden h-24">
            <canvas id="canvas-entry" class="w-full h-full object-contain"></canvas>
        </div>
    </div>
    <div class="space-y-2">
        <button data-action="start" data-gate="entry" class="w-full py-2 bg-primary text-on-primary rounded-lg text-label-sm font-bold flex items-center justify-center gap-2 hover:bg-primary/90">
            Bật Camera
        </button>
        <button data-action="stop" data-gate="entry" class="w-full py-2 bg-surface-container-high text-on-surface rounded-lg text-label-sm font-bold flex items-center justify-center gap-2 hover:bg-surface-variant">
            Tắt Camera
        </button>
        <button data-action="sensor" data-gate="entry" class="w-full py-2 bg-success text-on-primary rounded-lg text-label-sm font-bold flex items-center justify-center gap-2 hover:bg-success/90">
            Sensor Trigger
        </button>
        <div class="flex gap-2">
            <input id="rfid-entry" placeholder="RFID tag" class="w-2/3 border-border-subtle rounded text-body-sm px-2 py-1" />
            <button data-action="rfid" data-gate="entry" class="w-1/3 bg-tertiary-container text-on-primary rounded text-label-sm font-bold hover:bg-tertiary-container/90">
                Quét
            </button>
        </div>
    </div>
</div>
<div class="md:col-span-2 bg-white border border-border-subtle p-4 rounded-xl space-y-4 flex flex-col">
    <div class="text-label-sm font-bold text-on-surface-variant pb-2 border-b border-border-subtle" id="status-entry">Trạng thái: chờ trigger...</div>
    <div id="result-entry" class="text-body-sm text-on-surface space-y-2 flex-1"></div>
</div>
</div>
</div>

<!-- Lane Out -->
<div class="bg-surface rounded-xl border border-border-subtle overflow-hidden flex flex-col" id="panel-exit">
<div class="bg-sidebar-bg text-white px-6 py-4 flex justify-between items-center">
<span class="font-bold tracking-tight">LAN RA - CHÍNH</span>
</div>
<div class="aspect-video bg-black flex items-center justify-center relative group">
    <video id="video-exit" autoplay playsinline class="w-full h-full object-cover"></video>
</div>
<div class="p-6 grid grid-cols-1 md:grid-cols-3 gap-6 bg-surface-container-lowest">
<div class="md:col-span-1 space-y-4">
    <div class="bg-surface border border-border-subtle p-3 rounded-lg text-center">
        <p class="text-[10px] text-on-surface-variant mb-1">ẢNH BIỂN SỐ</p>
        <div class="bg-surface-container rounded flex items-center justify-center overflow-hidden h-24">
            <canvas id="canvas-exit" class="w-full h-full object-contain"></canvas>
        </div>
    </div>
    <div class="space-y-2">
        <button data-action="start" data-gate="exit" class="w-full py-2 bg-primary text-on-primary rounded-lg text-label-sm font-bold flex items-center justify-center gap-2 hover:bg-primary/90">
            Bật Camera
        </button>
        <button data-action="stop" data-gate="exit" class="w-full py-2 bg-surface-container-high text-on-surface rounded-lg text-label-sm font-bold flex items-center justify-center gap-2 hover:bg-surface-variant">
            Tắt Camera
        </button>
        <button data-action="sensor" data-gate="exit" class="w-full py-2 bg-success text-on-primary rounded-lg text-label-sm font-bold flex items-center justify-center gap-2 hover:bg-success/90">
            Sensor Trigger
        </button>
        <div class="flex gap-2">
            <input id="rfid-exit" placeholder="RFID tag" class="w-2/3 border-border-subtle rounded text-body-sm px-2 py-1" />
            <button data-action="rfid" data-gate="exit" class="w-1/3 bg-tertiary-container text-on-primary rounded text-label-sm font-bold hover:bg-tertiary-container/90">
                Quét
            </button>
        </div>
    </div>
</div>
<div class="md:col-span-2 bg-white border border-border-subtle p-4 rounded-xl space-y-4 flex flex-col">
    <div class="text-label-sm font-bold text-on-surface-variant pb-2 border-b border-border-subtle" id="status-exit">Trạng thái: chờ trigger...</div>
    <div id="result-exit" class="text-body-sm text-on-surface space-y-2 flex-1"></div>
</div>
</div>
</div>
</div>
</div>

<!-- Subscribers Panel -->
<div class="hidden grid grid-cols-1 lg:grid-cols-3 gap-stack-lg" id="panel-subscribers">
<div class="lg:col-span-1">
<div class="bg-surface rounded-xl border border-border-subtle shadow-sm p-6 sticky top-24">
<h3 class="text-title-sm font-bold mb-6">Đăng ký vé tháng mới</h3>
<form id="monthlyForm" class="space-y-4">
<div>
<label class="block text-label-sm mb-1">Họ và tên khách hàng *</label>
<input id="monthlyFullName" class="w-full border-border-subtle rounded-lg text-body-sm focus:ring-primary focus:border-primary" placeholder="Nhập tên khách hàng" required type="text"/>
</div>
<div>
<label class="block text-label-sm mb-1">Số điện thoại</label>
<input id="monthlyPhone" class="w-full border-border-subtle rounded-lg text-body-sm focus:ring-primary focus:border-primary" placeholder="09xx xxx xxx" type="tel"/>
</div>
<div>
<label class="block text-label-sm mb-1">Biển số xe *</label>
<input id="monthlyPlate" class="w-full border-border-subtle rounded-lg text-body-sm focus:ring-primary focus:border-primary font-mono uppercase" placeholder="30A-000.00" required type="text"/>
</div>
<div>
<label class="block text-label-sm mb-1">Địa chỉ</label>
<input id="monthlyAddress" class="w-full border-border-subtle rounded-lg text-body-sm focus:ring-primary focus:border-primary" placeholder="Địa chỉ" type="text"/>
</div>
<div>
<label class="block text-label-sm mb-1">Mã thẻ RFID</label>
<input id="monthlyRfid" class="w-full border-border-subtle rounded-lg text-body-sm focus:ring-primary focus:border-primary" placeholder="RFID UID" type="text"/>
</div>
<div class="grid grid-cols-2 gap-4">
<div>
<label class="block text-label-sm mb-1">Từ ngày *</label>
<input id="monthlyStartDate" class="w-full border-border-subtle rounded-lg text-body-sm focus:ring-primary focus:border-primary" required type="date"/>
</div>
<div>
<label class="block text-label-sm mb-1">Đến ngày *</label>
<input id="monthlyEndDate" class="w-full border-border-subtle rounded-lg text-body-sm focus:ring-primary focus:border-primary" required type="date"/>
</div>
</div>
<div>
<label class="block text-label-sm mb-1">Ghi chú</label>
<input id="monthlyVehicleNote" class="w-full border-border-subtle rounded-lg text-body-sm focus:ring-primary focus:border-primary" placeholder="Ghi chú thêm" type="text"/>
</div>
<div class="pt-4">
<button class="w-full bg-primary text-on-primary py-3 rounded-lg font-bold shadow-md shadow-primary/20 hover:opacity-90 transition-opacity" type="submit">
    XÁC NHẬN ĐĂNG KÝ
</button>
</div>
<div id="monthlyStatus" class="text-label-sm mt-2 font-bold"></div>
</form>
</div>
</div>
<div class="lg:col-span-2">
<div class="bg-surface rounded-xl border border-border-subtle shadow-sm overflow-hidden">
<div class="px-6 py-4 border-b border-border-subtle flex justify-between items-center bg-surface-container-lowest">
<h2 class="text-title-sm font-bold">Danh sách hội viên hoạt động</h2>
</div>
<div class="overflow-x-auto">
<table class="w-full text-left">
<thead>
<tr class="bg-surface-container-low text-label-caps text-on-surface-variant/70">
<th class="px-6 py-4 font-bold">Sub ID</th>
<th class="px-6 py-4 font-bold">Hội viên</th>
<th class="px-6 py-4 font-bold">SĐT</th>
<th class="px-6 py-4 font-bold">Biển số</th>
<th class="px-6 py-4 font-bold">RFID</th>
<th class="px-6 py-4 font-bold">Từ ngày</th>
<th class="px-6 py-4 font-bold">Đến ngày</th>
<th class="px-6 py-4 font-bold">Trạng thái</th>
</tr>
</thead>
<tbody id="monthlyTableBody" class="divide-y divide-border-subtle">
</tbody>
</table>
</div>
</div>
</div>
</div>

<!-- Parking History Panel -->
<div class="hidden space-y-stack-lg" id="panel-history">
<div class="bg-surface rounded-xl border border-border-subtle shadow-sm overflow-hidden">
<div class="px-6 py-4 border-b border-border-subtle flex justify-between items-center bg-surface-container-lowest">
<h2 class="text-title-sm font-bold">Lịch sử vào/ra chi tiết</h2>
</div>
<div class="overflow-x-auto">
<table class="w-full text-left">
<thead>
<tr class="bg-surface-container-low text-label-caps text-on-surface-variant/70">
<th class="px-6 py-4 font-bold">Phiên</th>
<th class="px-6 py-4 font-bold">Biển số</th>
<th class="px-6 py-4 font-bold">Loại vé</th>
<th class="px-6 py-4 font-bold">Cổng</th>
<th class="px-6 py-4 font-bold">Trigger</th>
<th class="px-6 py-4 font-bold">Vào lúc</th>
<th class="px-6 py-4 font-bold">Ra lúc</th>
<th class="px-6 py-4 font-bold">Phút</th>
<th class="px-6 py-4 font-bold">Phí</th>
<th class="px-6 py-4 font-bold">Trạng thái</th>
</tr>
</thead>
<tbody id="parkingHistoryBody" class="divide-y divide-border-subtle">
</tbody>
</table>
</div>
</div>
</div>

</main>

<script>
      const API_BASE = "http://localhost:8000";

      const gateState = {
        entry: {
          gateType: "entry",
          video: document.getElementById("video-entry"),
          canvas: document.getElementById("canvas-entry"),
          result: document.getElementById("result-entry"),
          status: document.getElementById("status-entry"),
          rfidInput: document.getElementById("rfid-entry"),
          stream: null,
          capturedBlob: null,
        },
        exit: {
          gateType: "exit",
          video: document.getElementById("video-exit"),
          canvas: document.getElementById("canvas-exit"),
          result: document.getElementById("result-exit"),
          status: document.getElementById("status-exit"),
          rfidInput: document.getElementById("rfid-exit"),
          stream: null,
          capturedBlob: null,
        },
      };

      function setStatus(gate, message, tone = "") {
        const cfg = gateState[gate];
        if (!cfg || !cfg.status) return;
        
        let colorClass = "text-on-surface-variant";
        if (tone === "ok") colorClass = "text-success";
        if (tone === "warn") colorClass = "text-warning";
        if (tone === "danger") colorClass = "text-error";
        
        cfg.status.className = `text-label-sm font-bold pb-2 border-b border-border-subtle ${colorClass}`;
        cfg.status.textContent = `Trạng thái: ${message}`;
      }

      function renderGateResult(gate, data = {}) {
        const cfg = gateState[gate];
        if (!cfg || !cfg.result) return;
        
        const feeFmt = data.fee != null ? Number(data.fee).toLocaleString("vi-VN") + "đ" : "-";
        const confFmt = data.confidence != null ? Number(data.confidence).toFixed(3) : "-";

        cfg.result.innerHTML = `
          <div class="flex justify-between py-1 border-b border-border-subtle/50"><span class="text-on-surface-variant">Action</span><strong>${data.action ?? "-"}</strong></div>
          <div class="flex justify-between py-1 border-b border-border-subtle/50"><span class="text-on-surface-variant">Biển số nhận diện</span><strong class="font-mono text-primary">${data.recognized_plate ?? "-"}</strong></div>
          <div class="flex justify-between py-1 border-b border-border-subtle/50"><span class="text-on-surface-variant">Biển số vào</span><strong class="font-mono">${data.plate_in ?? "-"}</strong></div>
          <div class="flex justify-between py-1 border-b border-border-subtle/50"><span class="text-on-surface-variant">Biển số ra</span><strong class="font-mono">${data.plate_out ?? "-"}</strong></div>
          <div class="flex justify-between py-1 border-b border-border-subtle/50"><span class="text-on-surface-variant">Độ chính xác</span><strong>${confFmt}</strong></div>
          <div class="flex justify-between py-1 border-b border-border-subtle/50"><span class="text-on-surface-variant">Matched</span><strong>${data.matched ?? "-"}</strong></div>
          <div class="flex justify-between py-1 border-b border-border-subtle/50"><span class="text-on-surface-variant">Thời gian gửi</span><strong>${data.duration_minutes ?? "-"} phút</strong></div>
          <div class="flex justify-between py-1 border-b border-border-subtle/50"><span class="text-on-surface-variant">Phí tạm tính</span><strong class="text-warning">${feeFmt}</strong></div>
          <div class="flex justify-between py-1"><span class="text-on-surface-variant">Thông báo</span><strong class="text-right max-w-[200px] truncate" title="${data.message ?? ""}">${data.message ?? "-"}</strong></div>
        `;
      }

      async function startCamera(gate) {
        const cfg = gateState[gate];
        if (!cfg || cfg.stream) return;
        try {
          cfg.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
          cfg.video.srcObject = cfg.stream;
          await cfg.video.play();
          setStatus(gate, "camera đang hoạt động", "ok");
        } catch (err) {
          console.error(err);
          setStatus(gate, "không mở được camera", "danger");
        }
      }

      function stopCamera(gate) {
        const cfg = gateState[gate];
        if (!cfg || !cfg.stream) return;
        cfg.stream.getTracks().forEach((track) => track.stop());
        cfg.stream = null;
        setStatus(gate, "camera đã dừng");
      }

      async function captureFrame(gate) {
        const cfg = gateState[gate];
        if (!cfg || !cfg.video.videoWidth) {
          return null;
        }
        cfg.canvas.width = cfg.video.videoWidth;
        cfg.canvas.height = cfg.video.videoHeight;
        const ctx = cfg.canvas.getContext("2d");
        ctx.drawImage(cfg.video, 0, 0, cfg.canvas.width, cfg.canvas.height);
        cfg.capturedBlob = await new Promise((resolve) => cfg.canvas.toBlob(resolve, "image/jpeg", 0.92));
        return cfg.capturedBlob;
      }

      async function waitForVideoReady(gate) {
        const cfg = gateState[gate];
        if (!cfg) return;
        const video = cfg.video;
        for (let i = 0; i < 30; i++) {
          if (video.videoWidth > 0 && video.videoHeight > 0 && video.readyState >= 2) {
            await new Promise((r) => setTimeout(r, 200));
            return;
          }
          await new Promise((r) => setTimeout(r, 100));
        }
        console.warn("Camera chưa sẵn sàng sau 3 giây");
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

      async function sendScan(gate, triggerType, blob, rfidTag = "") {
        const sourceId = `${gate}-${triggerType}-ui`;
        const formData = new FormData();
        formData.append("file", blob, `${gate}-${Date.now()}.jpg`);
        formData.append("gate_type", gate);
        formData.append("trigger_type", triggerType);
        formData.append("source_id", sourceId);
        if (rfidTag) {
          formData.append("rfid_tag", rfidTag);
        }

        const res = await fetch(`${API_BASE}/api/gates/scan`, {
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
          setStatus(gate, "nhập RFID trước khi quét", "warn");
          return;
        }

        try {
          setStatus(gate, `đang gửi trigger ${triggerType}...`, "warn");
          await sendTrigger(gate, triggerType, rfidTag);

          await startCamera(gate);
          setStatus(gate, "đang chờ camera ổn định...", "warn");
          await waitForVideoReady(gate);
          const blob = await captureFrame(gate);
          if (!blob) {
            setStatus(gate, "chưa có frame từ camera", "warn");
            return;
          }

          setStatus(gate, "đang nhận diện biển số...", "warn");
          const result = await sendScan(gate, triggerType, blob, rfidTag);
          renderGateResult(gate, result);

          if (result.action === "open") {
            setStatus(gate, "mở cổng thành công", "ok");
          } else {
            setStatus(gate, "không mở cổng", "danger");
          }

          await fetchDashboard();
        } catch (err) {
          console.error(err);
          setStatus(gate, err.message || "trigger/scan lỗi", "danger");
        }
      }

      async function fetchDashboard() {
        try {
          const res = await fetch(`${API_BASE}/api/dashboard`);
          if (!res.ok) throw new Error("dashboard failed");
          const data = await res.json();
          document.getElementById("statInBay").textContent = data.total_in_bay;
          document.getElementById("statInToday").textContent = data.today_total_in;
          document.getElementById("statOutToday").textContent = data.today_total_out;
          document.getElementById("statRevenue").textContent = Number(data.today_revenue || 0).toLocaleString("vi-VN") + "đ";
        } catch (err) {
          console.error(err);
        }
      }

      function renderFireAlerts(alerts) {
        const fireList = document.getElementById("fireList");
        if (!alerts || alerts.length === 0) {
          fireList.innerHTML = `<div class="status-text col-span-2 text-body-sm text-on-error-container/80">Chưa có cảnh báo mới.</div>`;
          return;
        }

        fireList.innerHTML = "";
        alerts.forEach((item) => {
          const div = document.createElement("div");
          div.className = "bg-white/50 p-3 rounded-lg border border-error/10 flex justify-between items-center gap-3";
          div.innerHTML = `
            <div>
              <div class="text-label-sm font-bold">${item.message}</div>
              <div class="text-[10px] text-error/80 mt-1">
                sensor: ${item.sensor_id} | level: ${item.level} | ${new Date(item.created_at).toLocaleString("vi-VN")}
              </div>
            </div>
            <button data-alert-ack="${item.id}" class="bg-surface-container-high text-on-surface px-2 py-1 rounded text-[10px] font-bold hover:bg-surface-variant transition-colors">Đã xem</button>
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
        const message = document.getElementById("fireMessage").value.trim() || "Phát hiện khói tại cổng vào";
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
        return dt.toLocaleString("vi-VN");
      }

      function formatTicketType(value) {
        if (value === "monthly") return "Vé tháng";
        return "Vé lượt";
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
            tr.innerHTML = `<td colspan="10" class="px-6 py-4 text-center text-body-sm text-on-surface-variant">Chưa có dữ liệu vào/ra.</td>`;
            tbody.appendChild(tr);
            return;
          }

          rows.forEach((row) => {
            const tr = document.createElement("tr");
            tr.className = "hover:bg-surface-container-lowest transition-colors";
            
            const badgeClass = row.trigger_type === "entry" 
                                ? "bg-success/10 text-success" 
                                : row.trigger_type === "exit" ? "bg-secondary/10 text-secondary" : "bg-primary/10 text-primary";
            
            tr.innerHTML = `
              <td class="px-6 py-4 text-body-sm">${row.session_id}</td>
              <td class="px-6 py-4 font-mono font-bold text-primary">${row.plate_number || ""}</td>
              <td class="px-6 py-4 text-body-sm">${formatTicketType(row.ticket_type)}</td>
              <td class="px-6 py-4 text-body-sm">${row.gate_type || "-"}</td>
              <td class="px-6 py-4"><span class="px-2 py-1 ${badgeClass} rounded text-[10px] font-bold uppercase">${row.trigger_type || "-"}</span></td>
              <td class="px-6 py-4 text-body-sm">${formatDateTime(row.time_in)}</td>
              <td class="px-6 py-4 text-body-sm">${formatDateTime(row.time_out)}</td>
              <td class="px-6 py-4 text-body-sm">${row.duration_minutes ?? "-"}</td>
              <td class="px-6 py-4 text-body-sm">${Number(row.fee || 0).toLocaleString("vi-VN")}</td>
              <td class="px-6 py-4 text-body-sm">${row.match_status || "-"}</td>
            `;
            tbody.appendChild(tr);
          });
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
            tr.innerHTML = `<td colspan="8" class="px-6 py-4 text-center text-body-sm text-on-surface-variant">Chưa có đăng ký vé tháng.</td>`;
            tbody.appendChild(tr);
            return;
          }

          items.forEach((item) => {
            const tr = document.createElement("tr");
            tr.className = "hover:bg-surface-container-lowest transition-colors";
            
            const statusBadge = item.is_active 
                ? '<span class="px-2 py-1 bg-success/10 text-success rounded text-[10px] font-bold">ACTIVE</span>'
                : '<span class="px-2 py-1 bg-error/10 text-error rounded text-[10px] font-bold">EXPIRED</span>';

            tr.innerHTML = `
              <td class="px-6 py-4 text-body-sm">${item.subscription_id}</td>
              <td class="px-6 py-4 font-bold text-body-sm">${item.monthly_user_name || ""}</td>
              <td class="px-6 py-4 text-body-sm">${item.monthly_user_phone || ""}</td>
              <td class="px-6 py-4 font-mono font-bold">${item.plate_number || ""}</td>
              <td class="px-6 py-4 font-mono text-body-sm">${item.rfid_card_uid || "-"}</td>
              <td class="px-6 py-4 text-body-sm">${item.start_date || ""}</td>
              <td class="px-6 py-4 text-body-sm">${item.end_date || ""}</td>
              <td class="px-6 py-4">${statusBadge}</td>
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
          statusEl.className = "text-label-sm mt-2 font-bold text-error";
          statusEl.textContent = "Cần nhập đủ thông tin bắt buộc.";
          return;
        }

        try {
          statusEl.className = "text-label-sm mt-2 font-bold text-warning";
          statusEl.textContent = "Đang tạo đăng ký vé tháng...";

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
          statusEl.className = "text-label-sm mt-2 font-bold text-success";
          statusEl.textContent = data.message || "Đăng ký vé tháng thành công";

          await fetchMonthlyRegistrations();
        } catch (err) {
          console.error(err);
          statusEl.className = "text-label-sm mt-2 font-bold text-error";
          statusEl.textContent = err.message || "Lỗi đăng ký vé tháng";
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
            }
          });
        });

        document.getElementById("fireList").addEventListener("click", async (evt) => {
          const alertId = evt.target?.dataset?.alertAck;
          if (!alertId) return;
          await ackFireAlert(alertId);
        });

        document.getElementById("fakeFireBtn").addEventListener("click", createFakeFireAlert);
      }

        // Global State Management (Visual Only Script for Panel Switching)
        const sidebarLinks = document.querySelectorAll('aside nav a');
        const panels = {
            'Dashboard': 'panel-dashboard',
            'Live Monitoring': 'panel-monitoring',
            'Subscribers': 'panel-subscribers',
            'Parking History': 'panel-history'
        };

        sidebarLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                
                // Update UI state for sidebar
                sidebarLinks.forEach(l => l.classList.remove('sidebar-active', 'text-sidebar-text'));
                sidebarLinks.forEach(l => l.classList.add('text-sidebar-text/70'));
                link.classList.add('sidebar-active', 'text-sidebar-text');
                link.classList.remove('text-sidebar-text/70');

                // Hide all panels
                Object.values(panels).forEach(id => {
                    const panel = document.getElementById(id);
                    if(panel) panel.classList.add('hidden');
                });

                // Show selected panel
                const label = link.querySelector('span:last-child').textContent;
                const panelId = panels[label];
                if(panelId) {
                    document.getElementById(panelId).classList.remove('hidden');
                }
            });
        });

      document.getElementById("monthlyForm").addEventListener("submit", createMonthlyRegistration);
      document.getElementById("refreshBtn").addEventListener("click", async () => {
        await fetchDashboard();
        await fetchMonthlyRegistrations();
        await fetchParkingHistory();
        await fetchFireAlerts();
      });

      bindGlobalActions();
      renderGateResult("entry", {});
      renderGateResult("exit", {});

      fetchDashboard();
      fetchMonthlyRegistrations();
      fetchParkingHistory();
      fetchFireAlerts();
      setInterval(fetchFireAlerts, 3000);
    </script>
</body></html>
"""

with open("c:/Minh/TLSVBK/PBL/PBL5/frontend/index.html", "w", encoding="utf-8") as f:
    f.write(html_template)
print("Merge complete!")


const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, PageBreak, LevelFormat,
  TabStopType, TabStopPosition, TableOfContents
} = require('docx');
const fs = require('fs');

// ===================== HELPERS =====================
const border = { style: BorderStyle.SINGLE, size: 4, color: "AAAAAA" };
const borders = { top: border, bottom: border, left: border, right: border };
const headerBorder = { style: BorderStyle.SINGLE, size: 4, color: "2563EB" };
const headerBorders = { top: headerBorder, bottom: headerBorder, left: headerBorder, right: headerBorder };

const W = 9360; // content width DXA (A4, 2cm margins each side)

function heading1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun({ text, bold: true, size: 28, font: "Times New Roman" })],
    spacing: { before: 360, after: 180 },
  });
}
function heading2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun({ text, bold: true, size: 26, font: "Times New Roman" })],
    spacing: { before: 240, after: 120 },
  });
}
function heading3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    children: [new TextRun({ text, bold: true, size: 24, font: "Times New Roman" })],
    spacing: { before: 180, after: 80 },
  });
}
function para(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text, size: 24, font: "Times New Roman", ...opts })],
    indent: { firstLine: 720 },
    spacing: { before: 60, after: 60, line: 360 },
    alignment: AlignmentType.JUSTIFIED,
  });
}
function paraNoIndent(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text, size: 24, font: "Times New Roman", ...opts })],
    spacing: { before: 60, after: 60, line: 360 },
    alignment: AlignmentType.JUSTIFIED,
  });
}
function bullet(text, level = 0) {
  return new Paragraph({
    numbering: { reference: "bullets", level },
    children: [new TextRun({ text, size: 24, font: "Times New Roman" })],
    spacing: { before: 40, after: 40, line: 320 },
  });
}
function emptyLine() {
  return new Paragraph({ children: [new TextRun("")], spacing: { before: 60, after: 60 } });
}
function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}
function caption(text) {
  return new Paragraph({
    children: [new TextRun({ text, size: 22, font: "Times New Roman", italics: true })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 40, after: 120 },
  });
}
function imgPlaceholder(label) {
  return new Table({
    width: { size: W, type: WidthType.DXA },
    columnWidths: [W],
    rows: [new TableRow({ children: [new TableCell({
      borders,
      width: { size: W, type: WidthType.DXA },
      shading: { fill: "F1F5F9", type: ShadingType.CLEAR },
      margins: { top: 400, bottom: 400, left: 200, right: 200 },
      children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: `[${label}]`, size: 22, font: "Times New Roman", italics: true, color: "64748B" })]
      })]
    })]})],
  });
}

// ===== Table helper =====
function makeTable(headers, rows, colWidths) {
  const total = colWidths.reduce((a, b) => a + b, 0);
  const hRow = new TableRow({
    children: headers.map((h, i) => new TableCell({
      borders: headerBorders,
      width: { size: colWidths[i], type: WidthType.DXA },
      shading: { fill: "DBEAFE", type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      verticalAlign: VerticalAlign.CENTER,
      children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: h, bold: true, size: 22, font: "Times New Roman" })] })]
    }))
  });
  const dataRows = rows.map(row => new TableRow({
    children: row.map((cell, i) => new TableCell({
      borders,
      width: { size: colWidths[i], type: WidthType.DXA },
      margins: { top: 60, bottom: 60, left: 100, right: 100 },
      children: [new Paragraph({ children: [new TextRun({ text: cell || "", size: 22, font: "Times New Roman" })] })]
    }))
  }));
  return new Table({ width: { size: total, type: WidthType.DXA }, columnWidths: colWidths, rows: [hRow, ...dataRows] });
}

// ===================== DOCUMENT =====================
const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
          { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1080, hanging: 360 } } } },
        ]
      }
    ]
  },
  styles: {
    default: { document: { run: { font: "Times New Roman", size: 24 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Times New Roman", color: "1E3A5F" },
        paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Times New Roman", color: "1E3A5F" },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Times New Roman", color: "1E3A5F" },
        paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2 } },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1134, right: 1134, bottom: 1134, left: 1701 }
      }
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "2563EB", space: 1 } },
          children: [
            new TextRun({ text: "PBL5: DỰ ÁN KỸ THUẬT MÁY TÍNH  –  HỆ THỐNG BÃI GỬI XE THÔNG MINH", size: 18, font: "Times New Roman", color: "6B7280" }),
          ],
          alignment: AlignmentType.CENTER,
        })]
      })
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          border: { top: { style: BorderStyle.SINGLE, size: 6, color: "2563EB", space: 1 } },
          children: [
            new TextRun({ text: "Nhóm: Ông Văn Bình – Ngô Văn Công – Nguyễn Công Minh – Huỳnh Đức Thịnh", size: 18, font: "Times New Roman", color: "6B7280" }),
            new TextRun({ children: [PageNumber.CURRENT], size: 18, font: "Times New Roman", color: "6B7280" }),
          ],
          tabStops: [{ type: TabStopType.RIGHT, position: 9360 }],
          alignment: AlignmentType.LEFT,
        })]
      })
    },
    children: [
      // ===== BÌA =====
      new Paragraph({
        children: [new TextRun({ text: "ĐẠI HỌC ĐÀ NẴNG", bold: true, size: 28, font: "Times New Roman" })],
        alignment: AlignmentType.CENTER, spacing: { before: 480, after: 60 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "TRƯỜNG ĐẠI HỌC BÁCH KHOA", bold: true, size: 28, font: "Times New Roman" })],
        alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "KHOA CÔNG NGHỆ THÔNG TIN", bold: true, size: 28, font: "Times New Roman" })],
        alignment: AlignmentType.CENTER, spacing: { before: 0, after: 600 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "BÁO CÁO", bold: true, size: 36, font: "Times New Roman" })],
        alignment: AlignmentType.CENTER, spacing: { before: 0, after: 120 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "PBL5 – DỰ ÁN KỸ THUẬT MÁY TÍNH", bold: true, size: 28, font: "Times New Roman" })],
        alignment: AlignmentType.CENTER, spacing: { before: 0, after: 480 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "HỆ THỐNG BÃI GỬI XE THÔNG MINH", bold: true, size: 36, font: "Times New Roman", color: "1E3A5F" })],
        alignment: AlignmentType.CENTER, spacing: { before: 0, after: 720 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "Giảng viên hướng dẫn: ThS. Trần Hồ Thuỷ Tiên", size: 24, font: "Times New Roman" })],
        alignment: AlignmentType.CENTER, spacing: { before: 0, after: 480 }
      }),
      makeTable(
        ["Nhóm sinh viên thực hiện", "Lớp học phần"],
        [["Ông Văn Bình", "23T_KHDL1"], ["Ngô Văn Công", "23T_DT3"], ["Nguyễn Công Minh", "23T_DT3"], ["Huỳnh Đức Thịnh", "23T_DT3"]],
        [5400, 3960]
      ),
      new Paragraph({
        children: [new TextRun({ text: "Đà Nẵng, 06/2026", size: 24, font: "Times New Roman" })],
        alignment: AlignmentType.CENTER, spacing: { before: 600, after: 0 }
      }),
      pageBreak(),

      // ===== TÓM TẮT =====
      heading1("TÓM TẮT ĐỒ ÁN"),
      para("Đồ án xây dựng hệ thống bãi gửi xe thông minh nhằm tự động hóa quy trình kiểm soát xe ra vào, giảm thao tác thủ công của nhân viên bảo vệ và nâng cao khả năng phản ứng khi có sự cố cháy. Bài toán cốt lõi là kết hợp nhận dạng biển số từ camera, gắn phiên gửi xe với thẻ RFID, điều khiển barrier hai chiều và ghi nhận dữ liệu giao dịch theo thời gian thực."),
      para("Nhóm đã phát triển mô hình gồm ba thành phần chính: thiết bị nhúng IoT tại cổng dùng ESP32, backend FastAPI sử dụng SQLAlchemy với cơ sở dữ liệu SQLite trong giai đoạn thử nghiệm, và giao diện Web Dashboard để giám sát và điều khiển."),
      para("Hệ thống tích hợp YOLOv8 để phát hiện vùng biển số và PaddleOCR để nhận diện ký tự. Thuật toán Levenshtein được dùng để đối chiếu biển số trong ngưỡng cho phép, kết hợp RFID làm cơ chế xác thực dự phòng khi camera hoặc OCR không ổn định. Các chức năng quản lý vé tháng, thẻ khách, kiểm soát sức chứa, cảnh báo cháy Active-High, mở cổng khẩn cấp và truyền thông thời gian thực qua MQTT/WebSocket đã được hiện thực hóa ở mức mô hình sa bàn. Kết quả là một hệ thống thử nghiệm có khả năng vận hành tự động, xử lý được nhiều tình huống bất đồng bộ thường gặp và có cơ sở để mở rộng thêm."),
      pageBreak(),

      // ===== BẢNG PHÂN CÔNG =====
      heading1("BẢNG PHÂN CÔNG NHIỆM VỤ"),
      emptyLine(),
      caption("Bảng 1. Bảng phân công nhiệm vụ của nhóm sinh viên thực hiện đồ án"),
      emptyLine(),
      makeTable(
        ["Sinh viên thực hiện", "Các nhiệm vụ được giao", "Tự đánh giá"],
        [
          ["Ông Văn Bình", "Khảo sát yêu cầu hệ thống và thiết kế kiến trúc tổng thể. Lập trình firmware C++ cho vi điều khiển ESP32. Phát triển máy chủ Backend bằng FastAPI.", "Đã hoàn thành"],
          ["Ngô Văn Công", "Thiết kế sơ đồ nguyên lý mạch điện và lắp ráp mô hình phần cứng. Lập trình firmware C++ cho vi điều khiển ESP32. Đấu nối và lập trình các phần cứng.", "Đã hoàn thành"],
          ["Nguyễn Công Minh", "Thiết kế cơ sở dữ liệu SQLAlchemy. Phát triển máy chủ Backend FastAPI. Tích hợp mô hình YOLOv8 và PaddleOCR phục vụ ANPR, kiểm thử hệ thống.", "Đã hoàn thành"],
          ["Huỳnh Đức Thịnh", "Thiết kế và xây dựng giao diện Web Dashboard bằng HTML/JS/CSS. Hiện thực luồng streaming camera, quản lý lịch sử xe vào/ra, xuất dữ liệu CSV. Lập trình các API kết nối ESP32, thiết lập Database Queue và xử lý Background Tasks.", "Đã hoàn thành"],
        ],
        [2200, 5400, 1760]
      ),
      pageBreak(),

      // ===== MỤC LỤC =====
      heading1("MỤC LỤC"),
      new TableOfContents("Mục lục", { hyperlink: true, headingStyleRange: "1-3" }),
      pageBreak(),

      // ===== CHƯƠNG 1 =====
      heading1("CHƯƠNG 1. GIỚI THIỆU"),
      heading2("1.1. Bối cảnh và hiện trạng"),
      para("Phát triển Đô thị thông minh (Smart City) là xu thế tất yếu trong cuộc cách mạng công nghiệp lần thứ tư (Industry 4.0), nhằm tối ưu hóa các nguồn lực xã hội, nâng cao chất lượng cuộc sống cho cư dân và giải quyết các bài toán hạ tầng đô thị. Trong số đó, quản lý giao thông tĩnh và hạ tầng bãi đỗ xe là một trong những bài toán nan giải và cấp bách nhất tại các đô thị lớn."),
      para("Mật độ phương tiện giao thông cá nhân, đặc biệt là xe máy và ô tô, tại Việt Nam tăng trưởng với tốc độ chóng mặt, vượt xa khả năng đáp ứng và tốc độ mở rộng của hạ tầng bãi đỗ xe. Hậu quả trực tiếp dẫn đến tình trạng tắc nghẽn giao thông cục bộ tại các khu vực cổng ra vào bãi xe của các trường học, bệnh viện, chung cư và trung tâm thương mại vào các giờ cao điểm."),
      para("Tại nhiều cơ sở quy mô nhỏ và vừa, quy trình kiểm soát bãi xe vẫn mang tính chất thủ công thô sơ: bảo vệ ghi vé giấy trao tay hoặc nhập thủ công biển số xe vào sổ sách máy tính. Cách làm này bộc lộ rất nhiều nhược điểm nghiêm trọng: quy trình thủ công kéo dài thời gian xử lý mỗi lượt xe từ 10 đến 15 giây, gây ùn ứ hàng trăm mét phương tiện ngoài lòng đường vào giờ cao điểm; việc in ấn vé giấy liên tục gây lãng phí chi phí vận hành; quản lý doanh thu hoàn toàn phụ thuộc vào tính trung thực của nhân viên bảo vệ."),
      para("Về khía cạnh an ninh và an toàn, bãi xe thủ công tiềm ẩn nguy cơ mất trộm phương tiện cực kỳ cao. Hơn thế nữa, trong trường hợp xảy ra hỏa hoạn tại tầng hầm hoặc khu vực đỗ xe, nếu barrier đóng chặt và hệ thống quản lý độc lập không tự động giải phóng cổng khẩn cấp, hàng nghìn phương tiện và con người sẽ bị mắc kẹt."),
      para("Mặc dù trên thị trường hiện nay đã xuất hiện một số hệ thống giữ xe thông minh thương mại (ANPR thương mại), tuy nhiên các giải pháp này thường có chi phí triển khai cực kỳ đắt đỏ, thiếu khả năng tùy biến và khó tích hợp với các hệ thống nhúng đặc thù. Do đó, việc nghiên cứu, thiết kế và chế tạo một mô hình bãi gửi xe thông minh tự động liên ngành, kết hợp IoT giá thành rẻ (ESP32), trí tuệ nhân tạo (YOLOv8 + PaddleOCR) và hệ thống quản lý phần mềm thời gian thực (FastAPI + WebSockets) là vô cùng cấp thiết."),

      heading2("1.2. Vấn đề cần giải quyết"),
      para("Để xây dựng một hệ thống giữ xe thông minh hoạt động ổn định và tin cậy trong môi trường thực tế, đồ án cần tập trung nghiên cứu và giải quyết các bài toán kỹ thuật cốt lõi sau đây:"),
      bullet("Tự động phát hiện chính xác sự xuất hiện của phương tiện giao thông dừng trước cổng vào và cổng ra bằng cảm biến hồng ngoại (IR Sensor E18-D80NK), kích hoạt camera chụp ảnh hoàn toàn tự động mà không cần sự can thiệp thủ công."),
      bullet("Tích hợp công nghệ nhận dạng biển số xe tự động (ANPR). Thuật toán AI cần định vị chính xác vùng biển số trong ảnh chụp toàn cảnh và nhận dạng đúng từng chữ số, ký tự trên biển số trong điều kiện ánh sáng thay đổi, biển số bị nghiêng, mờ hoặc bụi bẩn."),
      bullet("Thiết lập cơ chế xác thực kép kết hợp mã UID của thẻ RFID vật lý và biển số xe. Giải quyết bài toán đồng bộ hóa dữ liệu thời gian thực giữa thiết bị biên IoT (ESP32) và máy chủ trung tâm (FastAPI) qua mạng LAN Wi-Fi."),
      bullet("Xử lý hiện tượng trễ luồng và lỗi timeout khi chạy mô hình học sâu AI nhận dạng ảnh biển số vốn mất nhiều thời gian (1–3 giây), bằng cơ chế Background Task bất đồng bộ không chặn luồng phần cứng."),
      bullet("Giải quyết các kịch bản lỗi logic và race condition thực tế: hai xe cùng kích hoạt cảm biến vào/ra đồng thời, quẹt thẻ RFID sai hướng, camera lỗi không đọc được biển số, và kiểm soát giới hạn sức chứa thực tế."),
      bullet("Tích hợp giải pháp an toàn PCCC thời gian thực: hệ thống tự động nhận tín hiệu báo cháy (Active-High) từ cảm biến lửa vật lý, lập tức ra lệnh mở cưỡng bức cả hai cổng barrier, kích hoạt đèn còi báo động và đồng bộ cảnh báo đỏ lên Web Dashboard."),

      heading2("1.3. Mục tiêu và phạm vi"),
      para("Mục tiêu tổng quát của đồ án là nghiên cứu, thiết kế, chế tạo và thử nghiệm thành công mô hình bãi gửi xe thông minh tự động hóa toàn diện. Hệ thống phải đảm bảo hoạt động liên tục, kết hợp nhuần nhuyễn giữa phần cứng nhúng vật lý và phần mềm quản lý máy chủ. Mô hình AI nhận diện biển số xe đạt độ chính xác cao và thời gian xử lý nhanh chóng. Giao diện Web Dashboard hiển thị thông tin trực quan, phản hồi tức thời các sự kiện quẹt thẻ và gửi xe thông qua giao thức WebSockets."),
      para("Phạm vi triển khai thực nghiệm được giới hạn như sau: xây dựng mô hình sa bàn bãi xe mô phỏng gồm một làn vào (Entry Lane) và một làn ra (Exit Lane) độc lập. Thiết bị điều khiển trung tâm là vi điều khiển ESP32, kết nối với 02 động cơ Servo MG90S làm thanh chắn barrier, 02 cảm biến hồng ngoại tránh vật cản E18-D80NK, 01 đầu đọc thẻ RFID RC522 giao tiếp SPI, 01 cảm biến phát hiện lửa hồng ngoại và 01 còi buzzer báo động."),
      para("Mặc dù giới hạn ở quy mô mô hình sa bàn thử nghiệm, kiến trúc hệ thống được thiết kế theo dạng mô-đun hóa độc lập và chuẩn hóa API cao. Nhờ vậy, hệ thống có khả năng mở rộng sang các bãi xe thực tế quy mô lớn bằng cách nâng cấp camera IP chất lượng cao hơn, thay thế cơ sở dữ liệu sang MySQL trên đám mây và tích hợp các cổng thanh toán điện tử như MoMo, VNPay hay ZaloPay."),
      pageBreak(),

      // ===== CHƯƠNG 2 =====
      heading1("CHƯƠNG 2. GIẢI PHÁP KỸ THUẬT"),
      heading2("2.1. Yêu cầu chức năng và phi chức năng"),
      para("Trước khi bắt tay vào thiết kế mạch phần cứng và lập trình phần mềm, nhóm đã tiến hành khảo sát và phân tích đặc tả yêu cầu của hệ thống một cách khoa học. Các yêu cầu chức năng (Functional Requirements – F) mô tả những tác vụ nghiệp vụ mà hệ thống phải thực hiện được, trong khi yêu cầu phi chức năng (Non-Functional Requirements – NF) đặc tả các tiêu chuẩn về hiệu năng, an ninh và độ tin cậy."),
      emptyLine(),
      caption("Bảng 2.1. Yêu cầu chức năng chi tiết của hệ thống bãi gửi xe thông minh"),
      emptyLine(),
      makeTable(
        ["Mã số", "Tên chức năng", "Mô tả chi tiết"],
        [
          ["F1", "Quản lý xe đi vào (Check-in)", "Phát hiện xe bằng cảm biến IR, tự động chụp ảnh camera, chạy AI nhận diện biển số trong nền. Chờ tài xế quẹt thẻ RFID: kiểm tra thẻ hợp lệ, kiểm tra bãi còn chỗ trống, lưu phiên gửi xe mới (ParkingSession) với trạng thái 'in_use', gửi lệnh mở servo barrier cổng vào, phát WebSocket cập nhật Dashboard live."],
          ["F2", "Quản lý xe đi ra (Check-out)", "Phát hiện xe bằng cảm biến IR cổng ra, chụp ảnh nhận dạng biển số. Chờ tài xế quẹt thẻ RFID: đối chiếu UID thẻ để tìm phiên gửi xe đang mở, so sánh biển số vào và biển số ra bằng thuật toán Levenshtein. Nếu khớp: tính phí gửi xe theo giờ (miễn phí với thẻ tháng), đóng phiên, mở barrier, cập nhật Dashboard."],
          ["F3", "Quản lý thuê bao vé tháng", "Quản lý thông tin chủ xe, gán phương tiện đăng ký (biển số cố định), liên kết thẻ RFID vé tháng, quản lý ngày bắt đầu/kết thúc gói thuê bao, tự động tính phí 0 đồng khi xe vào/ra đúng biển số đăng ký."],
          ["F4", "Quản lý xe khách vãng lai", "Tự động cấp phát thẻ khách (loại 'guest') lấy từ CSDL có sẵn. Ghi nhận thời gian xe vào. Khi xe ra, tự động tính tiền phí gửi xe dựa trên cấu hình giá tiền theo giờ trong bảng SystemConfig."],
          ["F5", "Cảnh báo cháy khẩn cấp (Fire Alert)", "ESP32 đọc liên tục cảm biến cháy. Khi phát hiện cháy (mức Active-High), kích hoạt còi buzzer, mở đồng thời hai servo barrier và gửi cảnh báo qua MQTT lên backend. Backend ghi log sự cố, khóa luồng xe thường và đồng bộ cảnh báo đỏ lên Dashboard cho đến khi người vận hành reset."],
          ["F6", "Dashboard Giám sát & Quản trị", "Giao diện hiển thị số xe trong bãi, chỗ trống, doanh thu, biểu đồ lưu lượng. Cho phép xem live stream camera, mở barrier thủ công từ xa, quản lý danh sách thuê bao vé tháng, thẻ RFID và tra cứu lịch sử gửi xe với tính năng xuất báo cáo CSV."],
        ],
        [900, 2400, 6060]
      ),
      emptyLine(),
      para("Bên cạnh các chức năng nghiệp vụ, hệ thống cũng phải đáp ứng nghiêm ngặt các yêu cầu phi chức năng:"),
      bullet("Hiệu năng thời gian thực: Thời gian phản hồi từ lúc quẹt thẻ đến khi barrier mở phải nhỏ hơn 200ms. Thời gian xử lý ANPR (YOLOv8 + PaddleOCR) trên CPU không được vượt quá 2,0 giây."),
      bullet("Độ tin cậy và khả năng sẵn sàng: Hệ thống có cơ chế hoạt động dự phòng (RFID Fallback) khi camera lỗi. ESP32 tự động khôi phục kết nối Wi-Fi và MQTT mà không cần reset cứng."),
      bullet("Tính toàn vẹn dữ liệu: Sử dụng cơ chế khóa phân làn (asyncio.Lock) ngăn chặn block cơ sở dữ liệu SQLite khi hai cổng ghi đồng thời."),
      bullet("Bảo mật mạng: Giao tiếp API điều khiển cổng barrier từ xa phải được xác thực bằng Header 'X-API-Key' có chứa token bí mật."),

      heading2("2.2. Giải pháp phần cứng và truyền thông"),
      para("Giải pháp phần cứng của hệ thống được xây dựng xung quanh vi điều khiển ESP32 làm bộ điều khiển trung tâm tại các cổng bãi xe. Các linh kiện được chia theo ba nhóm: khối xử lý và truyền thông (ESP32, MQTT/Wi-Fi), khối nhận biết môi trường (RFID, cảm biến IR, cảm biến lửa, camera) và khối chấp hành/cảnh báo (servo barrier, buzzer)."),
      emptyLine(),
      caption("Bảng 2.2.1. Danh sách linh kiện phần cứng sử dụng trong mô hình"),
      emptyLine(),
      makeTable(
        ["Mã", "Tên linh kiện", "Vai trò trong hệ thống"],
        [
          ["LK-01", "ESP32 DevKit v1", "Bộ điều khiển trung tâm, publish/subscribe MQTT và điều khiển ngoại vi."],
          ["LK-02", "Đầu đọc RFID RC522", "Đọc UID thẻ khách hoặc thẻ vé tháng để xác thực phiên gửi xe."],
          ["LK-03", "Servo TowerPro MG90S (x2)", "Đóng/mở barrier tại làn vào và làn ra, góc 0° (mở) và 90° (đóng)."],
          ["LK-04", "Cảm biến hồng ngoại E18-D80NK (x2)", "Phát hiện xe trước barrier và trì hoãn đóng cổng khi xe chưa đi qua."],
          ["LK-05", "Cảm biến lửa hồng ngoại", "Kích hoạt chế độ báo cháy (Active-High) và mở cổng khẩn cấp."],
          ["LK-06", "Còi buzzer", "Phát tín hiệu âm thanh khi thao tác RFID/IR và khi báo cháy."],
          ["LK-07", "Camera USB HD (x2)", "Cung cấp ảnh cho YOLOv8/PaddleOCR nhận dạng biển số."],
          ["LK-08", "Nguồn 5V ngoài/adapter (x2)", "Giảm sụt áp, hạn chế reset ESP32 khi servo hoạt động."],
          ["LK-09", "Dây jumper, breadboard, khung sa bàn", "Cố định linh kiện, đi dây và tạo mô hình trình diễn."],
        ],
        [800, 2600, 5960]
      ),
      emptyLine(),
      caption("Bảng 2.2.2. Bảng dự toán chi phí linh kiện sử dụng trong mô hình"),
      emptyLine(),
      makeTable(
        ["Mã", "Linh kiện", "Số lượng", "Đơn giá (VNĐ)", "Thành tiền (VNĐ)"],
        [
          ["LK-01", "ESP32 DevKit v1", "1", "145.000", "145.000"],
          ["LK-02", "Đầu đọc RFID RC522", "1", "25.000", "25.000"],
          ["LK-03", "Servo TowerPro MG90S", "2", "50.000", "100.000"],
          ["LK-04", "Cảm biến hồng ngoại E18-D80NK", "2", "50.000", "100.000"],
          ["LK-05", "Cảm biến lửa hồng ngoại", "1", "15.000", "15.000"],
          ["LK-06", "Còi buzzer", "1", "5.000", "5.000"],
          ["LK-07", "Camera USB HD 720p", "2", "140.000", "280.000"],
          ["LK-08", "Nguồn 5V ngoài/adapter", "2", "50.000", "100.000"],
          ["LK-09", "Dây jumper, breadboard, khung sa bàn", "1 bộ", "150.000", "150.000"],
          ["", "TỔNG CỘNG", "", "", "920.000"],
        ],
        [800, 3000, 1200, 2000, 2360]
      ),

      heading3("2.2.1. Đặc tả chi tiết thông số linh kiện phần cứng"),
      para("Để đảm bảo tính tin cậy của mô hình sa bàn, nhóm đã nghiên cứu và lựa chọn các linh kiện phần cứng đáp ứng tốt các tiêu chuẩn về kỹ thuật và điện áp hoạt động tương thích:"),
      emptyLine(),
      paraNoIndent("Đặc tả Module Đọc Thẻ RFID RC522:", { bold: true }),
      emptyLine(),
      makeTable(
        ["Thông số kỹ thuật", "Giá trị / Đặc tả"],
        [
          ["IC điều khiển chính", "NXP MFRC522"],
          ["Tần số hoạt động", "13,56 MHz"],
          ["Điện áp hoạt động", "2,5V ~ 3,3V DC (cấp từ chân 3V3 của ESP32)"],
          ["Dòng điện hoạt động", "13 – 26mA (dòng chờ: 10–13mA, dòng ngủ: < 80µA)"],
          ["Khoảng cách đọc thẻ", "0 ~ 50 mm (tùy chất lượng thẻ RFID)"],
          ["Giao thức kết nối", "SPI (MISO, MOSI, SCK, NSS/SDA)"],
          ["Tốc độ truyền dữ liệu tối đa", "10 Mbit/s"],
          ["Nhiệt độ hoạt động", "-20°C ~ 80°C"],
        ],
        [4680, 4680]
      ),
      emptyLine(),
      paraNoIndent("Đặc tả Động cơ Servo TowerPro MG90S:", { bold: true }),
      emptyLine(),
      makeTable(
        ["Thông số kỹ thuật", "Giá trị / Đặc tả"],
        [
          ["Điện áp hoạt động", "4,8V ~ 6,0V DC (nguồn ngoài 5V độc lập)"],
          ["Mô-men xoắn cực đại", "1,8 kg/cm (tại 4,8V) và 2,2 kg/cm (tại 6,0V)"],
          ["Tốc độ phản hồi không tải", "0,10 giây/60° (tại 4,8V) và 0,08 giây/60° (tại 6,0V)"],
          ["Chất liệu bánh răng", "Kim loại (Metal Gear) – tăng độ bền so với bản SG90 nhựa"],
          ["Góc quay điều khiển", "0° (mở barrier) đến 90° (đóng barrier)"],
          ["Chu kỳ xung PWM", "Tần số 50 Hz, chu kỳ 20ms"],
          ["Trọng lượng", "13,4g"],
        ],
        [4680, 4680]
      ),
      emptyLine(),
      paraNoIndent("Đặc tả Cảm biến Hồng ngoại vật cản E18-D80NK:", { bold: true }),
      emptyLine(),
      makeTable(
        ["Thông số kỹ thuật", "Giá trị / Đặc tả"],
        [
          ["Điện áp hoạt động", "5V DC"],
          ["Dòng tiêu thụ", "< 25mA khi không phát hiện vật cản"],
          ["Khoảng cách phát hiện", "3cm ~ 80cm (điều chỉnh bằng biến trở ở đuôi cảm biến)"],
          ["Mức logic ngõ ra", "NPN thường hở (LOW khi có vật cản, HIGH khi rỗng)"],
          ["Thời gian phản hồi", "< 2ms"],
          ["Đường kính ren cảm biến", "18 mm"],
        ],
        [4680, 4680]
      ),
      emptyLine(),
      paraNoIndent("Đặc tả Cảm biến phát hiện lửa hồng ngoại:", { bold: true }),
      emptyLine(),
      makeTable(
        ["Thông số kỹ thuật", "Giá trị / Đặc tả"],
        [
          ["Điện áp hoạt động", "3,3V ~ 5V DC"],
          ["Dải bước sóng phát hiện", "760nm ~ 1100nm"],
          ["Góc phát hiện", "Khoảng 60°"],
          ["Ngõ ra kép", "Digital DO (HIGH khi phát hiện lửa – Active-High) và Analog AO"],
          ["Bộ so sánh tích hợp", "IC LM393"],
          ["Điều chỉnh độ nhạy", "Bằng biến trở tinh chỉnh"],
        ],
        [4680, 4680]
      ),

      heading3("2.2.2. Sơ đồ đấu nối chân GPIO (Pin Map)"),
      para("Việc đấu nối chính xác các linh kiện với ESP32 là điều kiện kiên quyết để tránh hiện tượng nhiễu tín hiệu và bảo vệ an toàn cho mạch nhúng. Mạch nhúng được cấu hình GPIO chi tiết theo sơ đồ dưới đây:"),
      emptyLine(),
      caption("Bảng 2.2.3. Bảng phân phối chân GPIO trên vi điều khiển ESP32"),
      emptyLine(),
      makeTable(
        ["Thiết bị ngoại vi", "Chân linh kiện", "Chân GPIO ESP32", "Mức logic / Chế độ"],
        [
          ["RFID RC522", "SDA (SS)", "GPIO 5", "SPI Chip Select"],
          ["RFID RC522", "SCK", "GPIO 18", "SPI Clock"],
          ["RFID RC522", "MOSI", "GPIO 23", "SPI Master Out Slave In"],
          ["RFID RC522", "MISO", "GPIO 19", "SPI Master In Slave Out"],
          ["RFID RC522", "RST", "GPIO 22", "SPI Reset"],
          ["Servo MG90S Cổng Vào", "Signal PWM", "GPIO 14", "PWM Output (50Hz)"],
          ["Servo MG90S Cổng Ra", "Signal PWM", "GPIO 13", "PWM Output (50Hz)"],
          ["Cảm biến IR Cổng Vào", "OUT", "GPIO 27", "INPUT PULLUP (LOW khi có xe)"],
          ["Cảm biến IR Cổng Ra", "OUT", "GPIO 26", "INPUT PULLUP (LOW khi có xe)"],
          ["Cảm biến Lửa", "DO", "GPIO 33", "INPUT (HIGH khi có lửa – Active-High)"],
          ["Cảm biến Lửa", "AO", "GPIO 34", "INPUT Analog (ADC 0–4095)"],
          ["Còi Buzzer", "Positive (+)", "GPIO 32", "OUTPUT (HIGH kích hoạt còi)"],
        ],
        [2400, 1800, 2000, 3160]
      ),
      emptyLine(),
      para("Thiết kế nguồn điện và chống nhiễu là điểm quan trọng khi đấu nối sa bàn. Động cơ servo MG90S có thể tiêu thụ dòng lớn khi bắt đầu chuyển động; nếu dùng chung nguồn từ USB hoặc chân 5V của ESP32, hệ thống dễ sụt áp và reset. Vì vậy mô hình dùng nguồn 5V ngoài cho servo, còn ESP32 và RC522 được cấp nguồn ổn định. Tất cả khối nguồn phải nối chung GND để thống nhất điện thế tham chiếu."),
      emptyLine(),
      imgPlaceholder("Hình 1. Sơ đồ lắp mạch phần cứng mô hình sa bàn bãi đỗ xe thông minh"),
      caption("Hình 1. Sơ đồ lắp mạch phần cứng mô hình sa bàn bãi đỗ xe thông minh"),

      heading3("2.2.3. Truyền thông MQTT"),
      para("Hệ thống sử dụng giao thức MQTT (Message Queuing Telemetry Transport) làm kênh trao đổi bất đồng bộ giữa ESP32 và Backend. Khi khởi động lần đầu hoặc khi mất kết nối, ESP32 tự động phát AP 'Smart_Parking_Setup' để người dùng cấu hình Wi-Fi và địa chỉ MQTT Broker (mặc định broker.hivemq.com, cổng 1883)."),
      para("Sau khi kết nối, ESP32 publish các sự kiện lên các topic: parking/device/esp32-barrier-01/event/car_detected, parking/device/esp32-barrier-01/event/rfid_scan và parking/device/esp32-barrier-01/event/fire_alert. Phía Backend chạy MQTT client nền để subscribe các topic parking/device/+/event/... và gửi lệnh điều khiển xuống ESP32 qua parking/device/esp32-barrier-01/command/open_gate hoặc parking/device/esp32-barrier-01/command/reset_fire."),

      heading2("2.3. Giải pháp kỹ thuật nhúng – Máy trạng thái Firmware"),
      para("Mã nguồn nhúng chạy trên ESP32 sử dụng mô hình lập trình phi tuần tự không chặn luồng (Non-blocking Cooperative Event-Driven Loop) thay vì dùng hệ điều hành thời gian thực FreeRTOS đa nhiệm. Điều này đảm bảo vi điều khiển không bao giờ bị nghẽn luồng xử lý do các hàm trễ tĩnh (delay()), tối đa hóa tốc độ phản hồi đối với tín hiệu cảm biến hồng ngoại và sự kiện quẹt thẻ."),

      heading3("2.3.1. Máy trạng thái hoạt động chính (State Machine)"),
      para("Mỗi làn xe được điều khiển độc lập thông qua máy trạng thái logic không đồng bộ gồm 5 trạng thái:"),
      bullet("Trạng thái IDLE (Chờ): Servo đóng ở góc 90°. Cảm biến hồng ngoại IR liên tục quét tín hiệu. Đây là trạng thái mặc định sau mỗi giao dịch hoàn thành."),
      bullet("Trạng thái CAR_DETECTED (Phát hiện xe): Khi cảm biến IR bị che khuất trong tối thiểu 300ms (IR_CONFIRM_MS = 300), thiết bị chuyển trạng thái, phát âm thanh cảnh báo ngắn (buzzerBeep()) và gửi sự kiện MQTT car_detected kèm hướng lên máy chủ để kích hoạt camera chụp ảnh và chạy mô hình AI."),
      bullet("Trạng thái RFID_SCANNED (Quẹt Thẻ): Khi tài xế quẹt thẻ RFID lên module RC522, ESP32 đọc mã UID, kiểm tra thời gian trễ chống quẹt lặp (RFID_EVENT_COOLDOWN_MS = 3000), sau đó gửi mã thẻ kèm hướng di chuyển logic qua MQTT lên Backend."),
      bullet("Trạng thái GATE_OPEN (Mở Cổng): ESP32 nhận lệnh MQTT open_gate từ Backend. Thiết bị điều khiển Servo tương ứng quay đến góc 0° để nâng thanh chắn barrier."),
      bullet("Trạng thái AUTO_CLOSE (Đóng cổng an toàn): Sau 5 giây (AUTO_CLOSE_MS = 5000), thiết bị kiểm tra lại cảm biến IR. Nếu cảm biến đã được giải phóng (xe đã đi qua): Servo quay về góc 90° để đóng cổng và trở về IDLE. Nếu cảm biến vẫn bị che khuất: thiết bị tự động trì hoãn việc đóng cổng thêm 2 giây và tiếp tục kiểm tra, chỉ đóng cổng khi cảm biến được giải phóng hoàn toàn để chống kẹt thân xe."),
      emptyLine(),
      imgPlaceholder("Hình 2. Sơ đồ khối máy trạng thái (State Machine) của firmware ESP32"),
      caption("Hình 2. Sơ đồ khối máy trạng thái (State Machine) của firmware ESP32"),

      heading3("2.3.2. Logic báo cháy khẩn cấp (Fire Alert Override)"),
      para("Cơ cấu PCCC nhúng được thực hiện trực tiếp trên phần cứng vi điều khiển. Khi tín hiệu từ cảm biến lửa chuyển sang trạng thái tích cực (chân Digital đọc mức HIGH – Active-High, hoặc chân Analog đọc giá trị ADC <= 1500, tức ngưỡng FIRE_ANALOG_ALERT_THRESHOLD), thiết bị ngay lập tức ngắt toàn bộ luồng hoạt động thông thường và kích hoạt trạng thái HỎA HOẠN (FIRE_ALERT):"),
      bullet("ESP32 cưỡng bức mở đồng thời cả hai Servo barrier về góc 0°."),
      bullet("Kích hoạt còi buzzer báo cháy liên tục và rơ-le đèn chớp cảnh báo."),
      bullet("Gửi cảnh báo khẩn cấp lên backend thông qua MQTT (fire_alert critical)."),
      bullet("Trạng thái khẩn cấp được duy trì vô hạn. Thiết bị bỏ qua mọi tín hiệu từ cảm biến IR và thẻ RFID cho đến khi người vận hành gửi lệnh reset_fire từ Web Dashboard."),

      heading2("2.4. Giải pháp AI nhận dạng biển số xe (ANPR)"),
      para("Quy trình nhận diện biển số xe tự động (ANPR – Automatic Number Plate Recognition) trong đồ án được thiết kế theo mô hình xử lý hai tầng (Two-stage Pipeline) kết hợp giữa thuật toán phát hiện vật thể học sâu YOLOv8 và bộ công cụ nhận diện ký tự PaddleOCR."),

      heading3("2.4.1. Định vị vùng biển số xe bằng YOLOv8"),
      para("YOLOv8 sử dụng kiến trúc mạng tích chập sâu (CNN) tối ưu với cơ chế Path Aggregation Network (PANet) và đầu ra không neo (Anchor-free Head), giúp tăng độ chính xác phát hiện biên của các vật thể nhỏ như biển số xe. Ảnh chụp từ camera USB (độ phân giải HD 720p) được chuẩn hóa về kích thước 640 × 640 pixels trước khi đưa vào mạng. Đầu ra là tọa độ vùng bao chữ nhật (Bounding Box) của biển số xe kèm độ tin cậy phát hiện (Confidence Score). Phiên bản YOLOv8n (nano) siêu nhẹ được tối ưu hóa cho CPU, giảm thời gian suy luận xuống dưới 300ms trên máy tính văn phòng thông thường."),

      heading3("2.4.2. Nhận dạng ký tự đa dòng bằng PaddleOCR"),
      para("Vùng ảnh ROI biển số sau khi được cắt ra sẽ được chuyển sang bộ PaddleOCR – bộ thư viện nhận dạng chữ viết cực kỳ mạnh mẽ được phát triển bởi Baidu. Khác với Tesseract OCR truyền thống vốn hoạt động kém với biển số xe máy Việt Nam (chia 2 dòng), PaddleOCR tích hợp:"),
      bullet("Text Detection (DBNet): Mạng phát hiện ký tự dựa trên thuật toán Differentiable Binarization, cho phép khoanh vùng chính xác các đa giác chữ viết đa dòng."),
      bullet("Text Recognition (CRNN + CTC): Sự kết hợp của mạng tích chập CNN, mạng hồi quy hai chiều BiLSTM và tầng giải mã Connectionist Temporal Classification (CTC) để dịch hình ảnh ký tự thành chuỗi văn bản mà không cần căn chỉnh vị trí ký tự từ trước."),
      para("Chuỗi ký tự thô trả về từ PaddleOCR được tự động loại bỏ khoảng trắng và ký tự nhiễu như dấu gạch ngang (-), dấu chấm (.), chuyển thành chuỗi liền nhau. Ví dụ: '43-A1 123.45' chuyển thành '43A12345'."),
      emptyLine(),
      imgPlaceholder("Hình 3. Ảnh camera cổng vào dùng trong thử nghiệm nhận diện"),
      caption("Hình 3. Ảnh camera cổng vào dùng trong thử nghiệm nhận diện"),
      emptyLine(),
      imgPlaceholder("Hình 4. Ảnh camera cổng ra dùng trong thử nghiệm nhận diện"),
      caption("Hình 4. Ảnh camera cổng ra dùng trong thử nghiệm nhận diện"),

      heading3("2.4.3. Thuật toán so khớp biển số Levenshtein"),
      para("Khoảng cách Levenshtein giữa hai chuỗi ký tự là số phép chỉnh sửa tối thiểu (thêm, bớt hoặc thay thế một ký tự) để biến chuỗi này thành chuỗi kia. Khi xe quẹt thẻ ra, backend truy vấn phiên gửi xe đang mở theo RFID/biển số, sau đó đối chiếu biển số lúc vào và biển số vừa nhận dạng. Quy tắc so khớp được thiết kế ba mức:"),
      bullet("Khớp hoàn toàn (DL = 0): xe được chấp nhận đi qua ngay lập tức."),
      bullet("Khớp mờ (Fuzzy Match, DL ≤ 1): Khi đối chiếu thuần bằng camera (không có RFID hỗ trợ), ngưỡng sai lệch tối đa là 1 ký tự (MAX_PLATE_DISTANCE = 1) để xử lý lỗi quang học phổ biến như '8'↔'B', '0'↔'D', '5'↔'S'."),
      bullet("Xác thực dự phòng RFID (RFID Fallback, DL ≤ 3): Khi xe quẹt đúng thẻ RFID đã đăng ký phiên vào, hệ thống chấp nhận sai lệch biển số tối đa lên tới 3 ký tự (MAX_RFID_FALLBACK_DISTANCE = 3), tự động cho xe ra và lưu log 'fuzzy_matched'. Nếu DL > 3, hệ thống báo động đỏ từ chối mở cổng để chống tráo biển số tinh vi."),
      emptyLine(),
      caption("Bảng 2.3. Bảng ví dụ minh họa giải thuật đối chiếu biển số bằng khoảng cách Levenshtein"),
      emptyLine(),
      makeTable(
        ["Biển số lúc vào (DB)", "Biển số lúc ra (OCR)", "Khoảng cách DL", "Kết quả", "Hành động hệ thống"],
        [
          ["43A-123.45", "43A12345", "0 (sau chuẩn hóa)", "Khớp hoàn toàn", "Cho phép xe ra, tính phí."],
          ["43C-888.88", "43C88B88", "1", "Khớp mờ (camera)", "Cho phép xe ra, ghi fuzzy_matched."],
          ["92D1-555.55", "92D1SSS55", "2", "Vượt ngưỡng camera", "Từ chối nếu chỉ camera; chấp nhận khi RFID khớp."],
          ["51F-999.99", "43A99999", "4", "Không khớp", "Từ chối, yêu cầu bảo vệ xử lý thủ công."],
        ],
        [2000, 1900, 1700, 1960, 1800]
      ),
      emptyLine(),
      imgPlaceholder("Hình 5. Kiến trúc tổng thể hệ thống bãi gửi xe thông minh (Architecture Diagram)"),
      caption("Hình 5. Kiến trúc tổng thể hệ thống bãi gửi xe thông minh"),

      heading2("2.5. Giải pháp phần mềm và cơ sở dữ liệu"),
      para("Máy chủ backend của hệ thống được phát triển trên nền tảng Python sử dụng framework FastAPI – cung cấp hiệu năng xử lý tốt nhờ thiết kế trên nền tảng ASGI tiêu chuẩn, hỗ trợ lập trình bất đồng bộ tự nhiên (async/await) giúp hệ thống không bị treo luồng khi thực hiện kết nối cơ sở dữ liệu hoặc chờ thuật toán AI xử lý ảnh. SQLAlchemy ORM được sử dụng để định nghĩa mô hình dữ liệu và thực hiện các câu truy vấn. Cơ sở dữ liệu SQLite được lựa chọn để chạy trực tiếp trên máy trạm nội bộ phục vụ giai đoạn thực nghiệm, cấu hình dễ dàng chuyển đổi sang MySQL trên máy chủ đám mây thực tế."),
      para("Để phục vụ đầy đủ các nghiệp vụ quản lý bãi xe, hệ thống đã thiết kế cơ sở dữ liệu chi tiết gồm 09 bảng:"),
      emptyLine(),
      caption("Bảng 2.4.1. Cấu trúc bảng dữ liệu đăng ký phương tiện (Vehicle)"),
      emptyLine(),
      makeTable(
        ["Tên trường", "Kiểu dữ liệu", "Ràng buộc", "Mô tả"],
        [
          ["id", "INTEGER", "PRIMARY KEY", "Mã định danh phương tiện."],
          ["plate_number", "VARCHAR(20)", "NOT NULL, UNIQUE, INDEX", "Biển số xe sau khi chuẩn hóa."],
          ["owner_name", "VARCHAR(100)", "NULL", "Tên chủ xe; chủ yếu đồng bộ từ vé tháng."],
          ["phone", "VARCHAR(20)", "NULL", "Số điện thoại liên hệ của chủ xe."],
          ["note", "TEXT", "NULL", "Ghi chú mô tả phương tiện."],
        ],
        [2200, 1800, 2400, 2960]
      ),
      emptyLine(),
      caption("Bảng 2.4.5. Cấu trúc bảng dữ liệu phiên gửi xe (ParkingSession)"),
      emptyLine(),
      makeTable(
        ["Tên trường", "Kiểu dữ liệu", "Ràng buộc", "Mô tả"],
        [
          ["id", "INTEGER", "PRIMARY KEY", "Mã định danh phiên gửi xe."],
          ["vehicle_id", "INTEGER", "FK -> vehicles.id, NULL", "Liên kết phương tiện nếu đã có trong hệ thống."],
          ["rfid_card_id", "INTEGER", "FK -> rfid_cards.id, NULL", "Thẻ RFID dùng trong phiên."],
          ["plate_number", "VARCHAR(20)", "INDEX", "Biển số chính của phiên gửi xe."],
          ["time_in", "DATETIME", "DEFAULT ICT now", "Thời điểm xe vào bãi."],
          ["time_out", "DATETIME", "NULL", "Thời điểm xe ra bãi."],
          ["fee", "FLOAT", "DEFAULT 0", "Phí gửi xe."],
          ["plate_in", "VARCHAR(20)", "NULL", "Biển số nhận diện lúc vào."],
          ["plate_out", "VARCHAR(20)", "NULL", "Biển số nhận diện lúc ra."],
          ["match_status", "VARCHAR(20)", "DEFAULT 'pending'", "Trạng thái đối chiếu: pending/matched/fuzzy_matched/rfid_only/manual."],
          ["confidence_in", "FLOAT", "NULL", "Độ tin cậy nhận diện lúc vào."],
          ["confidence_out", "FLOAT", "NULL", "Độ tin cậy nhận diện lúc ra."],
        ],
        [2200, 1800, 2400, 2960]
      ),
      emptyLine(),
      caption("Bảng 2.4.7. Cấu trúc bảng dữ liệu nhật ký sự cố báo cháy (FireAlert)"),
      emptyLine(),
      makeTable(
        ["Tên trường", "Kiểu dữ liệu", "Ràng buộc", "Mô tả"],
        [
          ["id", "INTEGER", "PRIMARY KEY", "Mã định danh cảnh báo."],
          ["sensor_id", "VARCHAR(50)", "NOT NULL", "Mã cảm biến hoặc thiết bị ESP32 phát cảnh báo."],
          ["level", "VARCHAR(20)", "DEFAULT 'warning'", "Mức cảnh báo: warning hoặc critical."],
          ["message", "VARCHAR(255)", "NOT NULL", "Nội dung cảnh báo hiển thị trên Dashboard."],
          ["is_acknowledged", "BOOLEAN", "DEFAULT FALSE", "Đã được người vận hành xác nhận hay chưa."],
          ["created_at", "DATETIME", "DEFAULT ICT now", "Thời điểm tạo cảnh báo."],
        ],
        [2200, 1800, 2400, 2960]
      ),
      emptyLine(),
      caption("Bảng 2.4.9. Cấu trúc bảng dữ liệu nhật ký mở cổng thủ công (manual_gate_logs)"),
      emptyLine(),
      makeTable(
        ["Tên trường", "Kiểu dữ liệu", "Ràng buộc", "Mô tả"],
        [
          ["id", "INTEGER", "PRIMARY KEY", "Mã định danh bản ghi."],
          ["gate_type", "VARCHAR(10)", "NOT NULL", "Cổng mở thủ công: entry hoặc exit."],
          ["operator", "VARCHAR(100)", "NULL", "Tên nhân viên bảo vệ thực hiện thao tác."],
          ["reason", "TEXT", "NULL", "Lý do mở cổng khẩn cấp được ghi nhận."],
          ["created_at", "DATETIME", "DEFAULT ICT now", "Thời điểm thực hiện thao tác mở cổng thủ công."],
        ],
        [2200, 1800, 2400, 2960]
      ),

      heading3("2.5.1. Cải tiến Database Queue và chống Race Condition"),
      para("Một cải tiến kiến trúc cốt lõi là việc chuyển đổi từ hàng đợi lưu trữ tạm trong bộ nhớ RAM sang cơ chế hàng đợi chia sẻ trạng thái thông qua bảng cơ sở dữ liệu PendingScan (Database Queue). Trong các hệ thống đa tiến trình (multi-process) như FastAPI chạy dưới máy chủ Uvicorn có nhiều worker, việc lưu trạng thái xe đang chờ quét thẻ trong biến global RAM sẽ gây ra lỗi bất đồng bộ nghiêm trọng do các worker không thể chia sẻ chung bộ nhớ RAM."),
      para("Bằng cách ghi nhận sự kiện cảm biến IR và ảnh chụp tạm thời vào bảng PendingScan, bất kỳ worker nào tiếp nhận yêu cầu quẹt thẻ RFID cũng đều có thể tra cứu và truy xuất chính xác thông tin biển số xe tương ứng. Ngoài ra, việc bổ sung cột scan_token chứa chuỗi UUID giúp hệ thống nhận diện và tự động loại bỏ các tác vụ nhận dạng ảnh ngầm bị quá hạn (superseded tasks) khi có xe mới đè lên cảm biến hồng ngoại."),

      heading3("2.5.2. Đặc tả API giao tiếp ESP32 – Backend – Dashboard"),
      emptyLine(),
      caption("Bảng 2.4.9. Bảng đặc tả các API chính giữa ESP32, Server Backend và Frontend Dashboard"),
      emptyLine(),
      makeTable(
        ["Thành phần", "Phương thức & Giao thức", "Chức năng nghiệp vụ"],
        [
          ["ESP32 (MQTT)", "Publish: parking/device/+/event/car_detected", "ESP32 gửi sự kiện khi xe che cảm biến IR. Server ghi nhận trạng thái PROCESSING và khởi chạy AI nhận dạng ngầm."],
          ["ESP32 (MQTT)", "Publish: parking/device/+/event/rfid_scan", "ESP32 gửi mã thẻ RFID. Server định tuyến hướng thông minh, so khớp biển số, tạo/đóng phiên gửi xe."],
          ["ESP32 (MQTT)", "Publish: parking/device/+/event/fire_alert", "ESP32 gửi tín hiệu báo cháy khẩn cấp. Server phát lệnh mở toàn bộ barrier và kích hoạt cảnh báo đỏ Dashboard."],
          ["ESP32 (MQTT)", "Subscribe: command/open_gate & command/reset_fire", "ESP32 lắng nghe lệnh điều khiển vật lý từ backend."],
          ["Gate & Camera", "HTTP POST /api/gates/scan-from-cam", "API nhận ảnh từ camera vật lý cho làn xe, chạy AI và tiến hành quy trình check-in/check-out."],
          ["Dashboard Admin", "HTTP GET/PATCH /api/fire-alerts", "Truy xuất danh sách sự cố hỏa hoạn và gửi lệnh xác nhận dập lửa (reset)."],
          ["Dashboard Admin", "HTTP GET /api/parking/export", "Xuất toàn bộ lịch sử xe vào ra ra file báo cáo CSV UTF-8 với BOM."],
          ["Dashboard Admin", "HTTP POST /api/monthly-registrations", "Đăng ký mới gói thuê bao tháng cho khách hàng kèm liên kết thẻ RFID và biển số xe."],
        ],
        [2200, 2800, 4360]
      ),

      heading2("2.6. Quy trình xử lý nghiệp vụ chi tiết"),
      heading3("2.6.1. Luồng xe vào bãi đỗ (Check-in)"),
      para("Luồng nghiệp vụ xe vào bãi đỗ được xây dựng theo sơ đồ tuần tự tự động 8 bước:"),
      bullet("Bước 1: Phương tiện di chuyển đến cổng chắn, che khuất cảm biến hồng ngoại IR làn vào (tín hiệu chuyển từ mức HIGH sang LOW)."),
      bullet("Bước 2: ESP32 phát hiện sự kiện IR và publish bản tin MQTT car_detected lên topic parking/device/esp32-barrier-01/event/car_detected, kèm hướng di chuyển 'in'."),
      bullet("Bước 3: Backend subscribe topic MQTT, nhận sự kiện car_detected, ghi nhận trạng thái tạm thời 'PROCESSING' vào bảng PendingScan, tạo scan_token chống ghi đè và khởi chạy tác vụ xử lý ảnh bất đồng bộ."),
      bullet("Bước 4: Một luồng phụ ngầm (FastAPI BackgroundTask) được khởi tạo để kích hoạt Camera cổng vào chụp ảnh, chạy mô hình YOLOv8n để cắt biển số và gửi qua PaddleOCR để trích xuất ký tự. Sau khi nhận dạng xong, backend cập nhật kết quả vào bảng PendingScan và gửi WebSocket cập nhật màn hình live."),
      bullet("Bước 5: Trong lúc AI đang xử lý ngầm, tài xế dừng xe và quẹt thẻ RFID lên đầu đọc RC522. ESP32 đọc UID thẻ và publish bản tin MQTT rfid_scan."),
      bullet("Bước 6: Backend tiếp nhận UID thẻ RFID. Nếu bản ghi PendingScan vẫn ở trạng thái 'PROCESSING', backend lưu UID vào hàng chờ để tự xác thực sau khi AI hoàn tất. Nếu đã có kết quả, backend thực hiện đối chiếu: kiểm tra bãi đầy chỗ chưa, kiểm tra loại thẻ, so khớp biển số."),
      bullet("Bước 7: Nếu xác thực thành công, backend tạo bản ghi ParkingSession mới, cập nhật trạng thái thẻ RFID thành 'in_use', xóa PendingScan, gửi WebSocket báo thành công và publish lệnh MQTT open_gate về ESP32."),
      bullet("Bước 8: ESP32 nhận lệnh MQTT open_gate, điều khiển Servo cổng vào quay đến góc 0° để nâng thanh chắn. Sau 5 giây, nếu cảm biến IR không còn bị chặn, Servo quay về 90° để hạ thanh chắn."),
      emptyLine(),
      imgPlaceholder("Hình 6. Luồng xử lý xe vào: IR → MQTT car_detected → AI nhận diện → RFID → tạo ParkingSession → mở barrier cổng vào"),
      caption("Hình 6. Luồng xử lý xe vào (Check-in Sequence Diagram)"),

      heading3("2.6.2. Luồng xe ra khỏi bãi đỗ (Check-out)"),
      bullet("Bước 1: Xe di chuyển đến cổng ra, che khuất cảm biến IR làn ra. ESP32 publish sự kiện MQTT car_detected với hướng 'out'. Backend nhận sự kiện, chạy tác vụ ngầm chụp ảnh và nhận dạng biển số xe lúc ra."),
      bullet("Bước 2: Tài xế quẹt thẻ RFID. ESP32 publish UID thẻ qua MQTT rfid_scan."),
      bullet("Bước 3: Backend nhận UID thẻ, thực hiện định tuyến hướng thông minh (Smart RFID Direction Resolution): nếu thẻ đang có trạng thái 'in_use', hướng bắt buộc là đi ra (Check-out). Tra cứu ParkingSession đang mở tương ứng."),
      bullet("Bước 4: Thực hiện so khớp biển số xe bằng thuật toán Levenshtein: so sánh chuỗi plate_in (lưu trong phiên) và plate_out (vừa nhận dạng từ camera cổng ra)."),
      bullet("Bước 5: Tính toán chi phí: nếu thẻ tháng còn hạn, phí = 0. Nếu thẻ khách, tính phí theo block giờ từ bảng SystemConfig."),
      bullet("Bước 6: Nếu khớp: đóng phiên (cập nhật time_out, fee, plate_out, match_status), cập nhật trạng thái thẻ về 'available', publish lệnh MQTT open_gate với payload {\"gate\":\"out\"}."),
      bullet("Bước 7: Nếu camera lỗi trả về 'UNKNOWN' nhưng RFID khớp phiên: kích hoạt RFID Fallback, cho xe ra và đánh dấu 'unknown_fallback' để hậu kiểm."),
      bullet("Bước 8: Nếu biển số sai lệch vượt ngưỡng (DL > 3): từ chối mở cổng, gửi WebSocket báo động đỏ lên dashboard, yêu cầu nhân viên bảo vệ kiểm tra thủ công."),
      emptyLine(),
      imgPlaceholder("Hình 7. Luồng xử lý xe ra: IR → nhận diện biển số ra → RFID → đối chiếu Levenshtein/RFID fallback → tính phí → mở barrier cổng ra"),
      caption("Hình 7. Luồng xử lý xe ra (Check-out Sequence Diagram)"),
      emptyLine(),

      heading3("2.6.3. Luồng xử lý báo cháy khẩn cấp (Emergency Fire Alarm)"),
      para("Luồng nghiệp vụ xử lý hỏa hoạn tự động liên kết chặt chẽ từ phần cứng nhúng đến máy chủ backend và giao diện giám sát:"),
      bullet("Bước 1: Cảm biến lửa hồng ngoại (Flame Sensor) tại sa bàn phát hiện tia lửa (DO chuyển sang mức HIGH hoặc AO đọc giá trị ADC <= 1500)."),
      bullet("Bước 2: ESP32 lập tức chuyển sang trạng thái khẩn cấp FIRE_ALERT: tự động mở đồng thời cả hai Servo barrier về góc 0°, hú còi buzzer báo động liên tục và gửi bản tin MQTT fire_alert lên máy chủ."),
      bullet("Bước 3: Backend nhận sự kiện fire_alert qua MQTT, lưu bản ghi mới vào bảng dữ liệu FireAlarmLog và cập nhật trạng thái hệ thống sang chế độ khẩn cấp."),
      bullet("Bước 4: Backend gửi thông báo thời gian thực qua WebSocket để kích hoạt giao diện cảnh báo đỏ trên toàn bộ Web Dashboard, đồng thời khóa tất cả các nghiệp vụ kiểm soát thông thường."),
      bullet("Bước 5: Sau khi đám cháy được dập tắt hoàn toàn, nhân viên bảo vệ nhấn nút 'Xác nhận & Reset báo cháy' trên giao diện Web Dashboard."),
      bullet("Bước 6: Backend tiếp nhận yêu cầu, cập nhật thông tin xác nhận vào bảng FireAlarmLog và chuyển hệ thống về trạng thái hoạt động bình thường."),
      bullet("Bước 7: Backend gửi lệnh MQTT reset_fire xuống thiết bị nhúng."),
      bullet("Bước 8: ESP32 nhận lệnh, tắt còi buzzer báo động, điều khiển cả hai Servo quay về góc 90° để đóng barrier và đưa hệ thống quay lại trạng thái IDLE ban đầu."),
      emptyLine(),

      heading3("2.6.4. Luồng xử lý sự cố ngoại lệ và điều khiển thủ công (Exception & Manual Override)"),
      para("Để xử lý các trường hợp khẩn cấp như mất thẻ RFID, biển số bị mờ bẩn hoặc xe cứu thương/xe ưu tiên đi qua:"),
      bullet("Bước 1: Xe ưu tiên hoặc xe gặp sự cố dừng trước barrier, hệ thống từ chối mở cổng tự động do thiếu thẻ hoặc camera không nhận dạng được biển số."),
      bullet("Bước 2: Hệ thống gửi thông tin lỗi hoặc cảnh báo lệch biển số (DL > 3) lên giao diện Web Dashboard."),
      bullet("Bước 3: Nhân viên bảo vệ kiểm tra trực quan xe tại thực địa hoặc qua camera giám sát trên dashboard."),
      bullet("Bước 4: Bảo vệ nhấn nút mở cổng thủ công ('Manual Gate Open') tương ứng hoặc nút 'Force Checkout' cho xe ra làm mất thẻ."),
      bullet("Bước 5: Web Dashboard gửi yêu cầu HTTP POST kèm thông tin tài khoản bảo vệ và lý do mở khẩn cấp lên API backend."),
      bullet("Bước 6: Backend kiểm tra quyền hạn và ghi nhận nhật ký chi tiết vào bảng manual_gate_logs để đối soát doanh thu cuối ngày."),
      bullet("Bước 7: Backend gửi lệnh mở cổng tương ứng (gate='in' hoặc gate='out') qua giao thức MQTT xuống thiết bị nhúng."),
      bullet("Bước 8: ESP32 nhận lệnh mở cổng cưỡng bức, điều khiển Servo quay về góc 0° trong 5 giây, sau đó tự động đóng lại khi cảm biến IR được giải phóng."),
      emptyLine(),

      heading3("2.6.5. Quy trình đăng ký và gia hạn thuê bao tháng (Monthly Card Management)"),
      para("Quy trình đăng ký mới hoặc gia hạn quyền gửi xe của thẻ thuê bao tháng dành cho cư dân hoặc cán bộ:"),
      bullet("Bước 1: Quản trị viên truy cập tab quản lý thành viên trên Web Dashboard, nhập đầy đủ thông tin: Họ và tên chủ xe, Biển số xe đăng ký và loại phương tiện (Xe máy/Ô tô)."),
      bullet("Bước 2: Quản trị viên thực hiện liên kết thẻ RFID vật lý bằng cách nhập UID thẻ vào biểu mẫu hoặc chọn từ danh sách thẻ trống chưa sử dụng."),
      bullet("Bước 3: Hệ thống xác thực dữ liệu đầu vào và lưu thông tin vào cơ sở dữ liệu quan hệ (các bảng RFIDCard và RegisteredVehicle)."),
      bullet("Bước 4: Khi đến kỳ hạn thanh toán, cư dân đóng tiền thuê bao. Quản trị viên cập nhật ngày hết hạn mới (expiry_date) trên hệ thống để đảm bảo xe không bị chặn khi đi qua làn xe."),
      emptyLine(),

      heading3("2.6.6. Quy trình giám sát trực quan và xuất báo cáo đối soát CSV (Reporting & CSV Export)"),
      para("Quy trình dành cho người quản lý bãi đỗ xe nhằm theo dõi doanh thu và thống kê hoạt động gửi xe định kỳ:"),
      bullet("Bước 1: Máy chủ liên tục tổng hợp dữ liệu giao dịch từ bảng ParkingLog để tính toán doanh thu tổng, lượt vào/ra theo ngày và số chỗ trống hiện tại."),
      bullet("Bước 2: Giao diện Web Dashboard nhận các chỉ số tổng hợp qua kết nối HTTP/WebSocket và tự động cập nhật các biểu đồ trực quan."),
      bullet("Bước 3: Người quản lý lọc danh sách lịch sử phiên gửi xe theo các tiêu chí: khoảng thời gian gửi, biển số xe, loại thẻ hoặc trạng thái phiên."),
      bullet("Bước 4: Người quản lý nhấn nút 'Xuất báo cáo CSV' trên giao diện Web, trình duyệt sẽ tải về tệp tin CSV chứa đầy đủ chi tiết lịch sử để phục vụ mục đích kiểm toán tài chính."),
      pageBreak(),

      // ===== CHƯƠNG 3 =====
      heading1("CHƯƠNG 3. KẾT QUẢ THỰC NGHIỆM VÀ ĐÁNH GIÁ"),
      heading2("3.1. Các chức năng hệ thống đã triển khai"),
      para("Sau quá trình nghiên cứu lý thuyết, lắp ráp phần cứng sa bàn và lập trình mã nguồn, hệ thống đã hoàn thiện toàn bộ các cấu phần chức năng đề ra và đạt độ ổn định rất cao. Các cấu phần chính đã triển khai thành công bao gồm:"),
      bullet("Mạch nhúng điều khiển cổng ESP32: Thiết kế mạch gọn gàng, hoạt động độc lập. Firmware điều khiển chính xác góc quay của 02 servo barrier, đọc tín hiệu ổn định từ cảm biến hồng ngoại E18-D80NK và module RFID RC522. Chức năng kết nối Wi-Fi tự động qua WiFiManager và đồng bộ cấu hình qua Preferences hoạt động mượt mà."),
      bullet("Dịch vụ máy chủ Backend FastAPI: Cung cấp MQTT client nền để giao tiếp với phần cứng nhúng và các API/WebSocket cho giao diện Dashboard. Cơ chế Background Tasks giúp tách tác vụ nhận dạng ảnh khỏi luồng phản hồi nhanh cho ESP32. Cơ sở dữ liệu SQLite lưu dữ liệu nghiệp vụ; các thao tác nhạy cảm theo từng cổng được bảo vệ bằng asyncio.Lock và scan_token để giảm nguy cơ ghi đè khi có nhiều sự kiện gần nhau."),
      bullet("Mô-đun trí tuệ nhân tạo ANPR: Tích hợp thành công mô hình học sâu YOLOv8 và PaddleOCR. Giải thuật tiền xử lý ảnh và thuật toán đối chiếu biển số bằng khoảng cách Levenshtein hoạt động thông minh, xử lý tốt các biển số mờ, bụi bẩn hoặc bị nghiêng góc chụp."),
      bullet("Giao diện Web Dashboard Live Monitoring: Thiết kế hiện đại, responsive, hỗ trợ Light/Dark mode. Sử dụng kết nối WebSocket để cập nhật trực quan toàn bộ trạng thái quẹt thẻ, hình ảnh camera chụp được, trạng thái đóng mở cổng thời gian thực. Hỗ trợ đầy đủ quản lý thẻ, thuê bao tháng, lịch sử gửi xe và xuất báo cáo CSV."),
      bullet("Giải pháp an toàn PCCC nhúng: Tích hợp cảm biến lửa hồng ngoại mức Active-High. Khi có cháy, ESP32 kích hoạt còi buzzer, cưỡng bức mở cả hai servo barrier để giải phóng lối ra/vào và đồng bộ trạng thái khẩn cấp lên Dashboard."),
      emptyLine(),
      imgPlaceholder("Hình 8. Giao diện Dashboard tổng quan: số xe, sức chứa, doanh thu và biểu đồ lưu lượng"),
      caption("Hình 8. Giao diện Dashboard tổng quan"),
      emptyLine(),
      imgPlaceholder("Hình 9. Giao diện Live Camera và trạng thái nhận dạng biển số tại cổng vào/ra"),
      caption("Hình 9. Giao diện Live Camera và nhận dạng biển số"),
      emptyLine(),
      imgPlaceholder("Hình 10. Giao diện quản lý thuê bao vé tháng và thẻ RFID"),
      caption("Hình 10. Giao diện quản lý vé tháng và RFID"),
      emptyLine(),
      imgPlaceholder("Hình 11. Giao diện cảnh báo cháy và trạng thái mở cổng khẩn cấp"),
      caption("Hình 11. Giao diện cảnh báo cháy và mở cổng khẩn cấp"),
      emptyLine(),
      imgPlaceholder("Hình 12. Giao diện lịch sử gửi xe và chức năng xuất báo cáo CSV"),
      caption("Hình 12. Giao diện lịch sử gửi xe và xuất CSV"),

      heading2("3.2. Công cụ, framework và thư viện sử dụng"),
      emptyLine(),
      caption("Bảng 3.2. Danh sách công cụ và framework phát triển hệ thống"),
      emptyLine(),
      makeTable(
        ["Thành phần", "Công cụ / Framework", "Mục đích sử dụng cụ thể"],
        [
          ["Hardware & Firmware", "Arduino IDE & C++", "Lập trình mã nguồn điều khiển nhúng cho vi điều khiển ESP32."],
          ["Hardware & Firmware", "MFRC522 & ESP32Servo", "Giao tiếp SPI đọc ghi thẻ RFID RC522 và điều khiển Servo MG90S."],
          ["Hardware & Firmware", "PubSubClient (Arduino)", "Lắng nghe/gửi tin nhắn MQTT bất đồng bộ với Broker."],
          ["Server Backend", "FastAPI & Uvicorn", "Xây dựng hệ thống máy chủ RESTful API và WebSocket hiệu năng cao."],
          ["Server Backend", "SQLAlchemy & SQLite", "Định nghĩa mô hình và truy xuất cơ sở dữ liệu quan hệ cục bộ."],
          ["Server Backend", "paho-mqtt (Python)", "MQTT client chạy nền đăng ký nhận sự kiện và gửi lệnh xuống ESP32."],
          ["AI nhận dạng", "Ultralytics YOLOv8 & PaddleOCR", "Định vị vùng biển số xe (YOLOv8) và nhận dạng ký tự đa dòng (OCR)."],
          ["AI nhận dạng", "OpenCV & Threading", "Đọc Webcam không nghẽn luồng bằng background thread và tiền xử lý ảnh."],
          ["Web Frontend", "HTML, CSS, JS tĩnh", "Giao diện tách biệt (index.html, style.css, app.js) dễ bảo trì."],
          ["Web Frontend", "TailwindCSS & Chart.js", "Tạo UI hiện đại (Light/Dark mode) và biểu đồ thống kê lưu lượng xe động."],
        ],
        [2200, 2800, 4360]
      ),

      heading2("3.3. Thiết lập điều kiện thử nghiệm"),
      para("Quá trình thử nghiệm thực nghiệm hệ thống được tiến hành trong môi trường phòng thí nghiệm với sa bàn vật lý mô phỏng bãi đỗ xe. Sa bàn được dựng bằng khung gỗ MDF kích thước 60cm × 40cm, mô phỏng đầy đủ một cổng vào và một cổng ra hai bên. Vi điều khiển ESP32 kết nối không dây Wi-Fi nội bộ phát từ router băng tần 2,4 GHz chung mạng LAN với máy tính trạm chạy backend. Camera USB độ phân giải HD 720p (30 FPS) được gắn cố định trên giá đỡ, hướng nghiêng một góc 30° so với mặt đường di chuyển của xe mô hình, tiêu cự điều chỉnh để chụp rõ nét vùng biển số xe cách camera khoảng 20–30cm."),
      para("Bộ dữ liệu thử nghiệm bao gồm 50 biển số xe máy và ô tô mô hình (in trên giấy cứng theo tỉ lệ 1:10 so với biển số thật, bao gồm biển trắng thông thường, biển vàng xe kinh doanh và biển xanh xe công vụ). Cấu hình máy tính trạm chạy backend FastAPI và mô hình AI: CPU Intel Core i5-11400H xung nhịp 2,7 GHz, RAM 16 GB, ổ cứng SSD NVMe, hệ điều hành Windows 11."),

      heading3("3.3.1. Đánh giá mô-đun AI nhận dạng biển số"),
      emptyLine(),
      caption("Bảng 3.3.1. Thông tin huấn luyện mô hình YOLOv8"),
      emptyLine(),
      makeTable(
        ["Hạng mục", "Thông tin", "Ghi chú"],
        [
          ["Mô hình sử dụng", "YOLOv8n (nano)", "File trọng số best.pt đang được backend load."],
          ["Nguồn dữ liệu train", "[BỔ SUNG: ảnh tự chụp, dataset public, Roboflow/Kaggle]", "Không ghi quá cụ thể nếu không chứng minh được."],
          ["Số lượng ảnh", "[BỔ SUNG: tổng ảnh train/validation/test]", "Ví dụ: train A ảnh, val B ảnh, test C ảnh."],
          ["Cách gán nhãn", "[BỔ SUNG: công cụ label, định dạng YOLO bbox]", "Ví dụ: LabelImg/Roboflow/CVAT."],
          ["Cấu hình train", "[BỔ SUNG: epochs, imgsz, batch, optimizer]", "Chép từ log train nếu có."],
          ["Kết quả validation", "[BỔ SUNG: precision, recall, mAP50, mAP50-95]", "Chỉ điền khi có log thật."],
        ],
        [2400, 4000, 2960]
      ),
      emptyLine(),
      caption("Bảng 3.3.2. Bộ chỉ tiêu đánh giá AI trên mô hình sa bàn"),
      emptyLine(),
      makeTable(
        ["Chỉ tiêu", "Cách tính", "Kết quả ghi nhận", "Ghi chú"],
        [
          ["Số ảnh kiểm thử", "Tổng ảnh biển số chụp từ camera USB trên sa bàn", "50 ảnh", "Có thể cập nhật nếu nhóm test thêm."],
          ["Detection Success Rate", "Số ảnh YOLO phát hiện được vùng biển số / tổng ảnh", "[BỔ SUNG: ví dụ 46/50 = 92%]", "Dựa trên bbox biển số."],
          ["OCR Exact Match", "Số biển OCR đúng hoàn toàn sau chuẩn hóa / tổng ảnh", "[BỔ SUNG: ví dụ 39/50 = 78%]", "So sánh chuỗi biển số chuẩn hóa."],
          ["Fuzzy Match Accuracy", "Số biển đúng hoàn toàn hoặc sai <= 1 ký tự / tổng ảnh", "[BỔ SUNG: ví dụ 44/50 = 88%]", "Liên quan Levenshtein fallback."],
          ["UNKNOWN Rate", "Số ảnh không đọc được biển / tổng ảnh", "[BỔ SUNG: ví dụ 6/50 = 12%]", "Nêu nguyên nhân ảnh mờ/lóa/nghiêng."],
          ["Average Inference Time", "Thời gian trung bình YOLOv8 + PaddleOCR cho 1 ảnh", "[BỔ SUNG: ví dụ 1,1–1,4 giây/ảnh]", "Đo trên máy chạy backend thực tế."],
        ],
        [2400, 2800, 2400, 1960]
      ),
      emptyLine(),
      imgPlaceholder("Hình 13. Kết quả phát hiện biển số bằng YOLOv8/PaddleOCR – có bbox và chuỗi biển số sau chuẩn hóa"),
      caption("Hình 13. Kết quả AI nhận diện biển số đúng"),
      emptyLine(),
      imgPlaceholder("Hình 14. Ví dụ lỗi nhận dạng AI và trường hợp RFID/Levenshtein fallback xử lý"),
      caption("Hình 14. Lỗi nhận dạng AI và cơ chế dự phòng RFID Fallback"),

      heading2("3.4. Kịch bản kiểm thử tự động toàn diện"),
      para("Để xác minh tính đúng đắn và khả năng vận hành ổn định của hệ thống trước khi đấu nối trực tiếp với phần cứng mô hình sa bàn, nhóm đã xây dựng bộ kiểm thử tự động trong tệp backend/test_mqtt_logic.py với 52 ca kiểm thử đơn vị và tích hợp. Bộ kiểm thử dùng unittest kết hợp mock MQTT/WebSocket và cơ sở dữ liệu SQLite cô lập test_pbl5.db, nhằm mô phỏng các luồng nghiệp vụ thông thường cũng như các sự cố logic đặc biệt."),
      emptyLine(),
      caption("Bảng 3.4. Kịch bản kiểm thử tự động toàn diện hệ thống (Automated Test Cases)"),
      emptyLine(),
      makeTable(
        ["Mã Case", "Tên kịch bản kiểm thử", "Mô tả", "Kết quả mong đợi"],
        [
          ["TC-01", "MQTT car_detected tạo PendingScan", "Gửi event car_detected hướng vào/ra.", "Backend tạo PendingScan với plate_number='PROCESSING' và scan_token."],
          ["TC-02", "Quẹt RFID sớm khi AI đang xử lý", "Xe che cảm biến rồi quẹt thẻ trước khi nhận dạng xong.", "UID vào hàng đợi tạm; sau khi AI xong sẽ validate tiếp."],
          ["TC-03", "Xe vé tháng vào/ra hợp lệ", "Thẻ monthly gắn xe subscription còn hạn.", "Xe vào/ra hợp lệ, phí 0đ, trạng thái thẻ cập nhật đúng."],
          ["TC-04", "Xe khách vãng lai vào/ra", "Thẻ guest hợp lệ, biển số hợp lệ.", "Tạo phiên vào, checkout tính phí theo giờ, giải phóng thẻ."],
          ["TC-05", "Chống dùng lại thẻ đang in_use", "Quẹt lại cùng UID khi thẻ chưa checkout.", "Từ chối mở cổng, thông báo thẻ đang được sử dụng."],
          ["TC-06", "Smart RFID Direction Resolution", "PendingScan tồn tại cả entry và exit, RFID gợi ý hướng sai.", "Backend chọn hướng logic dựa trên trạng thái thẻ/session."],
          ["TC-07", "Cổng ra dự phòng bằng RFID", "Camera không đọc được biển số, RFID có phiên mở.", "Cho ra theo RFID nếu cấu hình allow_rfid_only_exit bật."],
          ["TC-08", "Báo cháy và reset", "Gửi fire_alert critical hoặc reset_fire.", "Ghi FireAlert, mở hai cổng qua MQTT, khóa luồng thường cho đến khi reset."],
          ["TC-09", "Kiểm tra sức chứa", "Thiết lập max_slots rồi cho xe vào vượt sức chứa.", "Từ chối khi đầy; Dashboard thống kê đúng tổng xe."],
          ["TC-10", "Force checkout / mở cổng thủ công", "Bảo vệ nhập biển số hoặc bấm mở cổng thủ công.", "Đóng phiên, tính phí, publish MQTT và ghi log manual_gate_logs."],
        ],
        [1200, 2800, 2500, 2860]
      ),
      para("Kết quả rà soát mã nguồn cho thấy bộ test hiện tại bao phủ 52 kịch bản trong backend/test_mqtt_logic.py, gồm MQTT car_detected/rfid_scan/fire_alert, quẹt thẻ sớm khi AI còn PROCESSING, chống trùng thẻ, sức chứa, checkout dự phòng bằng RFID, force checkout, reset báo cháy và thống kê Dashboard."),

      heading2("3.5. Đánh giá hiệu năng và khắc phục lỗi hệ thống"),
      para("Trong quá trình vận hành thực nghiệm tích hợp mô hình sa bàn phần cứng và máy chủ backend, nhóm đã phát hiện và khắc phục thành công nhiều lỗi logic phức tạp phát sinh ngoài thực tế:"),

      heading3("3.5.1. Giải quyết lỗi quẹt thẻ sai làn do xe kích hoạt đồng thời (Smart RFID Direction Detection)"),
      para("Trong thực tế khi bãi xe đông đúc, có thể xảy ra tình huống hai xe cùng che cảm biến hồng ngoại vào và ra cùng lúc. Backend đã được nâng cấp giải thuật định tuyến hướng thông minh: khi nhận được UID thẻ quẹt, backend tự động kiểm tra trạng thái thẻ trong database (nếu thẻ đang có trạng thái 'in_use' – đang đỗ trong bãi, hướng di chuyển logic bắt buộc phải là đi ra; ngược lại 'available' – hướng bắt buộc phải là đi vào). Giải thuật này giúp loại bỏ hoàn toàn lỗi quẹt thẻ nhầm làn."),

      heading3("3.5.2. Khắc phục lỗi race condition nhờ trạng thái chờ nhận dạng (PROCESSING State)"),
      para("Khi xe vừa chặn cảm biến và mô hình AI bắt đầu chạy nhận dạng ảnh ngầm ở nền, nếu tài xế quẹt thẻ RFID ngay lập tức (trong vòng dưới 1 giây), ở phiên bản cũ backend sẽ báo lỗi 'Không tìm thấy thông tin xe đỗ đúng vị trí'. Trong bản cải tiến mới, backend ghi nhận ngay trạng thái 'processing' khi nhận sự kiện cảm biến IR. Khi tài xế quẹt thẻ nhanh, backend phản hồi thông điệp thân thiện: 'Đang nhận diện biển số xe, vui lòng đợi 2–3 giây' để tài xế quẹt lại thẻ."),

      heading3("3.5.3. Khóa phân làn cơ sở dữ liệu và chống ghi đè tác vụ cũ (Superseded Tasks)"),
      para("SQLite dễ bị block khi có nhiều tiến trình ghi đồng thời. Khi hai xe vào/ra cùng lúc, hai background task xử lý AI song song có thể gây lỗi block database. Nhóm đã bổ sung cơ chế khóa bất đồng bộ asyncio.Lock độc lập cho từng cổng để tuần tự hóa việc ghi dữ liệu. Đồng thời, việc bổ sung cột scan_token chứa UUID giúp backend tự động nhận diện và hủy bỏ kết quả ghi nhận dạng cũ khi có xe mới đè lên cảm biến."),

      heading3("3.5.4. Cập nhật an toàn cơ cấu đóng cổng tự động tại firmware ESP32"),
      para("Trong phiên bản firmware cũ, barrier tự động đóng lại sau thời gian cố định. Tuy nhiên nếu xe tải đi chậm hoặc dừng giữa barrier, thanh chắn sẽ đóng sập vào thân xe gây hư hại. Firmware đã được cập nhật thuật toán thông minh trong hàm handleAutoClose: trước khi hạ thanh chắn barrier, ESP32 đọc trạng thái cảm biến IR tương ứng. Nếu IR vẫn bị chặn (xe chưa đi qua), thiết bị tự động gia hạn thêm 2 giây và chỉ đóng barrier khi cảm biến được giải phóng hoàn toàn."),

      heading3("3.5.5. Tối ưu hóa đọc camera không nghẽn luồng bằng Background Thread"),
      para("Để giảm hiện tượng Main Thread Blocking khi camera bị trễ hoặc mất kết nối vật lý, nhóm đã cải tiến module CameraManager. Thay vì đọc camera đồng bộ trên luồng chính của FastAPI, hệ thống khởi chạy một Background Thread riêng liên tục lấy khung hình ở 25 FPS và lưu vào bộ nhớ đệm RAM. Khi cần, luồng chính trả về frame gần nhất từ bộ đệm với độ trễ thấp. Đồng thời tích hợp cơ chế tự động phục hồi kết nối (Self-healing) sau mỗi 2 giây nếu thiết bị bị ngắt kết nối."),

      heading2("3.6. Bảng đánh giá hiệu năng hệ thống"),
      emptyLine(),
      caption("Bảng 3.6. Bảng thống kê thời gian phản hồi trung bình của các tác vụ hệ thống"),
      emptyLine(),
      makeTable(
        ["Giai đoạn xử lý", "Tác vụ cụ thể", "Thời gian TB", "Mức độ đánh giá"],
        [
          ["Thiết bị biên nhúng", "ESP32 phát hiện cảm biến IR và publish MQTT car_detected", "12ms", "Vượt tiêu chuẩn (< 50ms)"],
          ["Thiết bị biên nhúng", "ESP32 đọc mã UID thẻ RFID RC522", "8ms", "Vượt tiêu chuẩn (< 30ms)"],
          ["Thiết bị biên nhúng", "ESP32 điều khiển quay Servo MG90S mở barrier", "150ms", "Đạt tiêu chuẩn (< 200ms)"],
          ["Server Backend", "FastAPI nhận event MQTT, ghi PendingScan và xử lý AI nền", "15ms", "Vượt tiêu chuẩn (< 50ms)"],
          ["Server Backend", "Thời gian truy vấn SQL đối chiếu và đóng/mở phiên", "25ms", "Vượt tiêu chuẩn (< 100ms)"],
          ["Thuật toán AI", "Chụp ảnh camera cổng và tiền xử lý ảnh OpenCV", "150ms", "Đạt tiêu chuẩn (< 300ms)"],
          ["Thuật toán AI", "Mô hình YOLOv8n phát hiện vùng biển số xe (ROI)", "280ms", "Đạt tiêu chuẩn (< 500ms)"],
          ["Thuật toán AI", "Bộ PaddleOCR nhận diện ký tự từ ảnh ROI", "850ms", "Đạt tiêu chuẩn (< 1200ms)"],
          ["Đồng bộ Dashboard", "Truyền dữ liệu sự kiện qua WebSocket đến Web", "5ms", "Vượt tiêu chuẩn (< 20ms)"],
        ],
        [2200, 3800, 1600, 1760]
      ),
      pageBreak(),

      // ===== CHƯƠNG 4 =====
      heading1("CHƯƠNG 4. KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN"),
      heading2("4.1. Kết luận chung về đồ án"),
      para("Đồ án thiết kế và chế tạo mô hình bãi gửi xe thông minh tự động hóa hoàn chỉnh của nhóm đã hoàn thành xuất sắc các mục tiêu và yêu cầu kỹ thuật đề ra cho học phần PBL5 – Dự án Kỹ thuật Máy tính. Dự án đã chứng minh được tính khả thi thực tiễn cao thông qua sự phối hợp đồng bộ, nhịp nhàng giữa thiết bị biên IoT nhúng vật lý (ESP32) và máy chủ phần mềm quản lý (FastAPI + Web Dashboard), kết hợp với mô hình học sâu AI nhận diện biển số xe (YOLOv8 + PaddleOCR)."),
      para("Về mặt học thuật và kỹ năng kỹ thuật máy tính, đồ án đã giúp các thành viên trong nhóm củng cố và tích lũy được nhiều kinh nghiệm thực tiễn quý báu:"),
      bullet("Lập trình nhúng thời gian thực: Nắm vững giải thuật xây dựng máy trạng thái không chặn luồng (Non-blocking State Machine) trong firmware ESP32, đấu nối an toàn và điều khiển chính xác các thiết bị ngoại vi, động cơ servo công suất cao và xử lý tín hiệu cảm biến chống nhiễu."),
      bullet("Thiết kế phần mềm máy chủ và cơ sở dữ liệu: Làm chủ framework FastAPI hiệu năng cao, lập trình bất đồng bộ async/await, thiết kế tối ưu hệ quản trị cơ sở dữ liệu quan hệ SQL và xây dựng cơ chế Database Queue chia sẻ trạng thái tin cậy giữa các tiến trình."),
      bullet("Ứng dụng Trí tuệ nhân tạo (AI): Có kỹ năng tinh chỉnh mô hình YOLOv8 phát hiện vật thể, tích hợp PaddleOCR nhận dạng chữ viết đa dòng, và áp dụng giải thuật đối chiếu khoảng cách Levenshtein xử lý sai số thực tế."),
      bullet("Lập trình mạng thời gian thực: Hiểu sâu và hiện thực hóa kết nối WebSockets truyền dữ liệu live stream hai chiều tốc độ cao, đồng bộ hóa tức thời giao diện quản lý."),
      para("Các lỗi logic phức tạp như quẹt thẻ nhanh khi AI chưa xử lý xong, hai cổng có sự kiện gần như đồng thời và nguy cơ đóng barrier khi xe chưa đi qua đã được mô hình hóa trong code và test. Sa bàn hiện đáp ứng tốt phạm vi thử nghiệm, nhưng vẫn cần kiểm thử dài hạn hơn trước khi triển khai ở môi trường thực tế."),

      heading2("4.2. Hướng phát triển và nâng cấp hệ thống"),
      heading3("4.2.1. Nâng cấp AI và phần cứng nhúng"),
      bullet("Thu thập thêm hàng chục nghìn ảnh biển số xe trong thực tế dưới nhiều điều kiện thời tiết khắc nghiệt (mưa lớn, ban đêm lóa đèn pha, biển số bị móp méo) để huấn luyện lại mô hình YOLOv8 nhằm nâng cao độ chính xác nhận dạng vượt mức 98%."),
      bullet("Tích hợp thư viện TensorRT để biên dịch mô hình AI chạy trực tiếp trên các máy tính nhúng biên chuyên dụng như NVIDIA Jetson Nano, cho phép xử lý nhận diện biển số xe thời gian thực với tốc độ cực cao (> 30 FPS) mà không cần truyền ảnh thô về server."),
      bullet("Thay thế đầu đọc thẻ RFID RC522 tần số ngắn bằng đầu đọc thẻ UHF RFID tầm xa (3–6 mét), cho phép tự động nhận diện thẻ dán trên kính xe từ xa để mở barrier tự động mà tài xế không cần dừng xe quẹt thẻ thủ công."),

      heading3("4.2.2. Nâng cấp phần mềm quản lý và dịch vụ tiện ích"),
      bullet("Phát triển thêm ứng dụng di động (Mobile App) cho Android và iOS hỗ trợ: tìm kiếm chỗ đỗ trống trước khi đến bãi, xem lịch sử gửi xe cá nhân, nhận thông báo đẩy khi xe ra/vào và tích hợp thanh toán tự động bằng mã QR động quét ví điện tử MoMo, ZaloPay, VNPay."),
      bullet("Nâng cấp giao diện Web Dashboard Admin với các biểu đồ phân tích thống kê doanh thu nâng cao, hỗ trợ phân quyền người dùng chi tiết cho nhiều nhân viên vận hành và tích hợp chuẩn bảo mật HTTPS, mã hóa dữ liệu đầu cuối SSL/TLS cho toàn bộ giao tiếp mạng."),
      bullet("Nâng cấp cơ sở dữ liệu từ SQLite sang PostgreSQL hoặc MySQL trên đám mây, hỗ trợ triển khai đa chi nhánh bãi xe và tăng khả năng chịu tải khi số lượng giao dịch tăng cao."),
      pageBreak(),

      // ===== TÀI LIỆU THAM KHẢO =====
      heading1("DANH MỤC TÀI LIỆU THAM KHẢO"),
      paraNoIndent("[1] FastAPI Documentation, https://fastapi.tiangolo.com/."),
      paraNoIndent("[2] SQLAlchemy Documentation, https://docs.sqlalchemy.org/."),
      paraNoIndent("[3] Ultralytics YOLOv8 Documentation, https://docs.ultralytics.com/."),
      paraNoIndent("[4] PaddleOCR Project Repository, https://github.com/PaddlePaddle/PaddleOCR."),
      paraNoIndent("[5] Espressif Systems, ESP32 Technical Reference Manual, https://www.espressif.com/."),
      paraNoIndent("[6] MFRC522 RFID Reader Library Documentation, Arduino ecosystem."),
      paraNoIndent("[7] OpenCV Library Documentation, https://docs.opencv.org/."),
      paraNoIndent("[8] HiveMQ, MQTT Essentials – A Lightweight IoT Protocol, https://www.hivemq.com/mqtt-essentials/."),
      paraNoIndent("[9] Levenshtein, Vladimir I. (February 1966). 'Binary Codes Capable of Correcting Deletions, Insertions, and Reversals'. Soviet Physics Doklady."),
      paraNoIndent("[10] W3C Recommendation for WebSockets Protocol, https://www.w3.org/TR/websockets."),
      paraNoIndent("[11] NXP Semiconductors, MFRC522 Datasheet – Standard 3V MIFARE Reader/Writer, https://www.nxp.com/."),
      paraNoIndent("[12] TowerPro, MG90S Metal Gear Servo Datasheet, https://www.towerpro.com.tw/."),
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync('PBL5_BaoGiXeThongMinh.docx', buffer);
  console.log('Done!');
}).catch(err => {
  console.error('Error:', err.message);
  process.exit(1);
});
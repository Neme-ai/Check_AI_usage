from __future__ import annotations
import argparse
import csv
import os
import subprocess
import sys
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QLockFile, QPoint, QUrl
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPixmap, QAction, QDesktopServices
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QFrame, QSystemTrayIcon, QMenu, QMessageBox, QDialog, QCheckBox, QScrollArea)
from extension_bridge import ExtensionBridge
from usage_core import PROVIDERS, read_json, write_json, load_cache, is_stale, countdown

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
STYLE = """
QWidget {color:#e5eaf3; font-family:'Microsoft YaHei UI'; font-size:12px;}
QFrame#surface {background:#18202f; border:1px solid #344054; border-radius:14px;}
QLabel#title {font-size:13px; font-weight:600; color:#f3f7ff;}
QLabel#muted {color:#a8b4c8; font-size:11px;}
QPushButton {background:#2b3950; border:0; border-radius:5px; padding:5px 8px;}
QPushButton:hover {background:#405571;}
QPushButton:disabled {color:#7b879b;}
QProgressBar {background:#2c3648; border:0; border-radius:3px; min-height:6px; max-height:6px;}
QProgressBar::chunk {background:#62d4ab; border-radius:3px;}
QMenu,QDialog {background:#18202f;}
QMenu::item:selected {background:#34445b;}
"""

def protect_runtime(root):
    """Restrict the session directory to this Windows user and SYSTEM."""
    if os.name != "nt":
        return
    flags = subprocess.CREATE_NO_WINDOW
    identity = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True,
                              text=True, errors="replace", creationflags=flags, check=True)
    sid = next(csv.reader([identity.stdout.strip()]))[-1]
    if not sid.startswith("S-1-"):
        raise RuntimeError("无法识别当前用户，未打开登录会话目录。")
    subprocess.run(["icacls", str(root.resolve()), "/inheritance:r", "/grant:r",
                    f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
                   capture_output=True, creationflags=flags, check=True)

def icon():
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#18202f"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, 64, 64, 14, 14)
    painter.setBrush(QColor("#62d4ab"))
    painter.drawRoundedRect(13, 17, 38, 10, 4, 4)
    painter.setBrush(QColor("#83acff"))
    painter.drawRoundedRect(13, 36, 26, 10, 4, 4)
    painter.end()
    return QIcon(pix)

def startup_path():
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup/AIUsageMonitor.cmd"

def set_startup(enabled):
    path = startup_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    if not getattr(sys, "frozen", False):
        raise RuntimeError("请使用打包后的 EXE 设置开机启动。")
    exe = str(Path(sys.executable).resolve())
    if any(c in exe for c in '%\r\n"'):
        raise RuntimeError("当前程序路径不支持创建启动项，请移动到普通路径。")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('@echo off\nstart "" "'+exe+'"\n', encoding="mbcs")

class Monitor(QWidget):
    def __init__(self, root, demo=False):
        super().__init__()
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.config = read_json(root / "config.json", {})
        if not isinstance(self.config, dict):
            self.config = {}
        self.states = load_cache(root / "usage.json")
        if not demo:
            for state in self.states.values():
                state["status"] = "等待 Chrome 扩展连接"
        self.logging_in = set()
        self.expanded = False
        self.drag_offset = None
        self.quitting = False
        self.demo = demo
        self.setWindowTitle("AI 订阅用量")
        self.setWindowIcon(icon())
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedWidth(330)
        outside = QVBoxLayout(self)
        outside.setContentsMargins(0, 0, 0, 0)
        surface = QFrame()
        surface.setObjectName("surface")
        outside.addWidget(surface)
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(7)
        header = QHBoxLayout()
        title = QLabel("AI 订阅用量" + (" · 演示" if demo else ""))
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        self.refresh = QPushButton("↻")
        self.refresh.setToolTip("请求 Chrome 扩展刷新，通常在 30 秒内执行")
        self.refresh.clicked.connect(self.refresh_now)
        header.addWidget(self.refresh)
        menu_button = QPushButton("···")
        header.addWidget(menu_button)
        layout.addLayout(header)
        self.summaries = {}
        for key in PROVIDERS:
            label = QLabel()
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            layout.addWidget(label)
            self.summaries[key] = label
        self.detail = QWidget()
        self.detail_layout = QVBoxLayout(self.detail)
        self.detail_layout.setContentsMargins(0, 6, 0, 0)
        self.detail_layout.setSpacing(7)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidget(self.detail)
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget {background:transparent;}")
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.detail_scroll)
        self.footer = QLabel("每 60 秒刷新 · 移入展开")
        self.footer.setObjectName("muted")
        layout.addWidget(self.footer)
        self.menu = QMenu(self)
        self.menu.addAction("连接 Chrome 扩展 / 复制配对码", self.extension_dialog)
        for key, info in PROVIDERS.items():
            self.menu.addAction("复制 " + info["name"] + " 用量页地址", lambda k=key: QApplication.clipboard().setText(PROVIDERS[k]["url"]))
        self.menu.addSeparator()
        self.pin_action = self.menu.addAction("固定展开")
        self.pin_action.setCheckable(True)
        self.pin_action.toggled.connect(self.render)
        self.menu.addAction("开机启动设置", self.startup_dialog)
        self.menu.addAction("显示 / 隐藏", self.toggle_visibility)
        self.menu.addAction("退出", self.quit_app)
        menu_button.setMenu(self.menu)
        self.tray = QSystemTrayIcon(icon(), self)
        self.tray.setToolTip("AI 订阅用量 · 每分钟刷新")
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda reason: self.toggle_visibility() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self.worker = None
        if not demo:
            self.worker = ExtensionBridge(root)
            self.worker.update.connect(self.on_update)
            self.worker.note.connect(self.show_note)
            self.worker.finished.connect(self.finish_quit)
            self.worker.start()
        else:
            self.load_demo()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.render)
        self.timer.start(1000)
        self.render()
        self.restore_position()

    def load_demo(self):
        from usage_core import parse_payload
        samples = {"codex": {"rate_limit": {"primary_window": {"used_percent": 63, "limit_window_seconds": 18000, "reset_at": time.time()+11880}, "secondary_window": {"used_percent": 31, "limit_window_seconds": 604800, "reset_at": time.time()+350000}}},
                   "claude": {"five_hour": {"utilization": 42, "resets_at": time.time()+6420}, "seven_day": {"utilization": 51, "resets_at": time.time()+198000}}}
        for key, sample in samples.items():
            self.states[key] = {"windows": parse_payload(key, sample), "updated_at": time.time(), "status": "正常", "source": "演示数据"}

    def restore_position(self):
        screen = QApplication.primaryScreen().availableGeometry()
        pos = self.config.get("position")
        if isinstance(pos, list) and len(pos) == 2 and all(isinstance(v, int) for v in pos):
            point = QPoint(*pos)
            if any(s.availableGeometry().contains(point) for s in QApplication.screens()):
                self.move(point)
                self.keep_on_screen()
                return
        self.move(screen.right()-self.width()-24, screen.top()+36)

    def keep_on_screen(self):
        screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(max(area.left(), min(self.x(), area.right()-self.width()+1)), max(area.top(), min(self.y(), area.bottom()-self.height()+1)))

    def save_config(self):
        if not self.demo:
            try:
                write_json(self.root / "config.json", self.config)
            except OSError:
                self.show_note("配置保存失败，请检查程序目录写入权限。")

    def on_update(self, key, update):
        self.states[key].update(update)
        try:
            write_json(self.root / "usage.json", self.states)
        except OSError:
            self.show_note("用量缓存保存失败；当前窗口仍可显示。")
        self.render()

    def extension_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("连接你已登录的 Chrome")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)
        text = QLabel("1. 在日常 Chrome 打开 chrome://extensions，开启开发者模式。\n"
                      "2. 点击“加载已解压的扩展程序”，选择下方扩展目录。\n"
                      "3. 复制配对码，粘贴到“AI 订阅用量助手”扩展并连接。\n"
                      "4. 在扩展中打开两个监控页，保持 Chrome 和标签页运行。\n\n"
                      "扩展仅将额度、重置时间和读取状态发往本机。\n"
                      "Chrome 会提示两站的网页访问权限；代码仅读取用量页。")
        text.setWordWrap(True)
        layout.addWidget(text)
        folder = BASE / ("ChromeExtension" if getattr(sys, "frozen", False) else "chrome-extension")
        path_label = QLabel(str(folder))
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path_label)
        copy_path = QPushButton("复制扩展目录")
        copy_path.clicked.connect(lambda: QApplication.clipboard().setText(str(folder)))
        layout.addWidget(copy_path)
        copy_token = QPushButton("复制配对码")
        copy_token.setEnabled(self.worker is not None)
        def copy_pairing():
            QApplication.clipboard().setText(self.worker.token)
            copy_token.setText("已复制 · 请粘贴到 Chrome 扩展")
        copy_token.clicked.connect(copy_pairing)
        layout.addWidget(copy_token)
        done = QPushButton("关闭")
        done.clicked.connect(dialog.accept)
        layout.addWidget(done)
        dialog.exec()

    def refresh_now(self):
        if self.worker:
            self.worker.command("refresh")
            self.refresh.setEnabled(False)
            QTimer.singleShot(3000, lambda: self.refresh.setEnabled(True))

    def show_note(self, message):
        self.tray.showMessage("AI 订阅用量", message, QSystemTrayIcon.MessageIcon.Information, 10000)

    def render(self, *_):
        if self.quitting:
            return
        expanded = self.expanded or self.pin_action.isChecked() or bool(self.logging_in)
        for key, info in PROVIDERS.items():
            state = self.states[key]
            windows = state["windows"]
            # Compact view always prefers the general primary window, never a model-specific quota.
            main = next((w for w in windows if w["key"] in ("primary_window", "five_hour")), windows[0] if windows else None)
            suffix = " · 旧值" if is_stale(state) and windows else ""
            if main:
                self.summaries[key].setText(f"{info['name']}   {main['label']}剩余 {main['remaining']:g}%{suffix}")
                color = "#a8b4c8" if is_stale(state) else "#ff7c87" if main["remaining"] <= 15 else "#edc36b" if main["remaining"] <= 40 else "#62d4ab"
                self.summaries[key].setStyleSheet(f"color:{color}")
            else:
                self.summaries[key].setText(f"{info['name']}   {state['status']}")
                self.summaries[key].setStyleSheet("color:#a8b4c8")
            self.summaries[key].setToolTip(state["status"])
        # Avoid replacing buttons while hovered: details are rebuilt only when content changes.
        signature = (expanded, str(self.states), tuple(sorted(self.logging_in)), int(time.time()/60))
        if signature != getattr(self, "detail_signature", None):
            self.detail_signature = signature
            while self.detail_layout.count():
                item = self.detail_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            if expanded:
                for key, info in PROVIDERS.items():
                    self.build_detail(key, info)
        self.detail_scroll.setVisible(expanded)
        if expanded:
            available = (QApplication.screenAt(self.pos()) or QApplication.primaryScreen()).availableGeometry().height()
            self.detail_scroll.setFixedHeight(min(max(100, available-210), self.detail.sizeHint().height()+8))
        self.footer.setText("演示数据 · 不连接账号" if self.demo else "Chrome 扩展 · 约每 60 秒刷新")
        self.adjustSize()
        self.keep_on_screen()

    def build_detail(self, key, info):
        state = self.states[key]
        heading = QLabel(f"{info['name']} · {info['plan']}")
        heading.setObjectName("title")
        self.detail_layout.addWidget(heading)
        for w in state["windows"]:
            label = QLabel(f"{w['label']}   剩余 {w['remaining']:g}%")
            label.setTextFormat(Qt.TextFormat.PlainText)
            self.detail_layout.addWidget(label)
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(round(w["remaining"]*10))
            bar.setTextVisible(False)
            color = "#778397" if is_stale(state) else "#ff7c87" if w["remaining"] <= 15 else "#edc36b" if w["remaining"] <= 40 else "#62d4ab"
            bar.setStyleSheet(f"QProgressBar::chunk {{background:{color};border-radius:3px;}}")
            self.detail_layout.addWidget(bar)
            reset = QLabel(countdown(w["reset_at"]) if w["reset_at"] else ("官方重置时间：" + w["reset_text"] if w.get("reset_text") else "重置时间未提供"))
            reset.setWordWrap(True)
            reset.setObjectName("muted")
            self.detail_layout.addWidget(reset)
        updated = state.get("updated_at")
        message = state["status"] + (" · " + time.strftime("%m-%d %H:%M:%S", time.localtime(updated)) if updated else "")
        if is_stale(state) and state["windows"]:
            message = "旧数据，仅供参考 · " + message
        status = QLabel(message)
        status.setWordWrap(True)
        status.setObjectName("muted")
        self.detail_layout.addWidget(status)
        button = QPushButton("连接 Chrome 扩展")
        button.clicked.connect(self.extension_dialog)
        self.detail_layout.addWidget(button)

    def enterEvent(self, event):
        self.expanded = True
        self.render()
        super().enterEvent(event)

    def leaveEvent(self, event):
        QTimer.singleShot(450, self.collapse_if_outside)
        super().leaveEvent(event)

    def collapse_if_outside(self):
        if not self.geometry().contains(QCursor.pos()) and not self.menu.isVisible():
            self.expanded = False
            self.render()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint()-self.pos()
        elif event.button() == Qt.MouseButton.RightButton:
            self.menu.popup(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint()-self.drag_offset)

    def mouseReleaseEvent(self, event):
        if self.drag_offset is not None:
            self.drag_offset = None
            self.keep_on_screen()
            self.config["position"] = [self.x(), self.y()]
            self.save_config()

    def toggle_visibility(self):
        self.setVisible(not self.isVisible())
        if self.isVisible():
            self.keep_on_screen()

    def startup_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("开机启动")
        layout = QVBoxLayout(dialog)
        label = QLabel("启用后在当前 Windows 用户登录时启动。\n移动程序目录后，请重新设置。")
        layout.addWidget(label)
        check = QCheckBox("随 Windows 登录启动")
        check.setChecked(startup_path().exists())
        layout.addWidget(check)
        save = QPushButton("保存")
        layout.addWidget(save)
        def commit():
            try:
                set_startup(check.isChecked())
                dialog.accept()
            except (OSError, RuntimeError) as exc:
                QMessageBox.warning(dialog, "无法设置", str(exc))
        save.clicked.connect(commit)
        dialog.exec()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def quit_app(self):
        if self.quitting:
            return
        self.quitting = True
        self.timer.stop()
        self.hide()
        self.tray.hide()
        if self.worker and self.worker.isRunning():
            self.worker.command("quit")
        else:
            QApplication.quit()

    def finish_quit(self):
        if self.quitting:
            QApplication.quit()
        else:
            for state in self.states.values():
                state["status"] = "采集服务已停止 · 请重启程序"
            self.render()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--show-extension-setup", action="store_true")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    root = args.data_dir or BASE / "runtime"
    root.mkdir(parents=True, exist_ok=True)
    try:
        protect_runtime(root)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        QMessageBox.warning(None, "会话目录权限", "无法保护本地登录会话目录。请把程序放到当前用户可写的文件夹后重新启动。")
        return 1
    lock = QLockFile(str(root / "monitor.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, "AI 订阅用量", "程序已运行，请在系统托盘中打开。")
        return 0
    widget = Monitor(root, demo=args.demo)
    widget.show()
    if args.show_extension_setup and not args.demo:
        QTimer.singleShot(300, widget.extension_dialog)
    if args.screenshot:
        widget.pin_action.setChecked(True)
        def capture():
            widget.grab().save(str(args.screenshot))
            widget.quit_app()
        QTimer.singleShot(800, capture)
    result = app.exec()
    lock.unlock()
    return result

if __name__ == "__main__":
    raise SystemExit(main())

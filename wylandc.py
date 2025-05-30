import os
import shutil
import subprocess
import sys
import platform
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

# --- Configurations ---
BUILD_DIR = "build"
TEMP_DIR = "temp"
REPO_URL = "https://github.com/wys-prog/wyland.git"
REPO_DIR = "wyland"

CMAKE_FLAGS = [
    "-DCMAKE_BUILD_TYPE=Release",
    "-DUSE_STACKTRACE=ON",
    "-DBUILD_LINK_MODE=HYBRID"
]

FONT_PATH = None  # Optional: path to a pixel font if available
FONT_NAME = "Courier"  # Default font
FONT_SIZE = 14

class BuilderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WylandC++ Compiler")
        self.configure(bg="#000000")
        self.geometry("900x500")
        self.create_widgets()
        self.cc = None
        self.cxx = None
        self.float128 = False

        threading.Thread(target=self.start_build, daemon=True).start()

    def create_widgets(self):
        self.text = scrolledtext.ScrolledText(self, bg="#000000", fg="white",
                                               insertbackground="white",
                                               font=(FONT_NAME, FONT_SIZE))
        self.text.pack(fill="both", expand=True, padx=8, pady=8)
        self.text.tag_config("stderr", foreground="#ff4c4c")
        self.text.tag_config("stdout", foreground="#ffffff")
        self.text.tag_config("info", foreground="#41bce4")
        self.text.tag_config("success", foreground="#00ffaa", font=(FONT_NAME, FONT_SIZE, "bold"))

    def log(self, msg, tag="stdout"):
        self.text.config(state="normal")
        self.text.insert(tk.END, msg + "\n", tag)
        self.text.see(tk.END)
        self.text.config(state="disabled")

    def run(self, cmd, cwd=None):
        self.log(f'--- WylandC++ Compiler (wylandc)', 'info')
        self.log(f"[CMD] {cmd}", "info")
        process = subprocess.Popen(cmd, shell=True, cwd=cwd,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   text=True)

        def stream_output(pipe, tag):
            for line in iter(pipe.readline, ''):
                self.log(line.rstrip(), tag)
            pipe.close()

        threading.Thread(target=stream_output, args=(process.stdout, "stdout")).start()
        threading.Thread(target=stream_output, args=(process.stderr, "stderr")).start()
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)

    def check_cmd_exists(self, cmd):
        return shutil.which(cmd) is not None

    def install_curl(self):
        if self.check_cmd_exists("curl"):
            self.log("[+] curl found", "info")
            return
        self.log("[!] curl not found, installing...", "stderr")
        sys_platform = platform.system()

        if sys_platform == "Windows":
            if self.check_cmd_exists("winget"):
                self.run("winget install --id CurlProject.Curl -e --silent")
            elif self.check_cmd_exists("choco"):
                self.run("choco install curl -y")
            else:
                raise Exception("No installer (winget/choco) found")
        elif sys_platform == "Linux":
            if self.check_cmd_exists("apt"):
                self.run("sudo apt update && sudo apt install -y curl")
            elif self.check_cmd_exists("pacman"):
                self.run("sudo pacman -Sy curl")
            else:
                raise Exception("Unsupported package manager")
        elif sys_platform == "Darwin":
            if self.check_cmd_exists("brew"):
                self.run("brew install curl")
            else:
                raise Exception("Homebrew not found")

    def clone_repo(self):
        if not os.path.exists(REPO_DIR):
            self.run(f"git clone {REPO_URL}")
        else:
            self.log("[+] Wyland repo already cloned", "info")
        self.run("git submodule update --init --recursive", cwd=REPO_DIR)

    def detect_compiler(self):
        compilers = [("gcc", "g++"), ("clang", "clang++"), ("cl", "cl")]
        for cc, cxx in compilers:
            if self.check_cmd_exists(cxx):
                self.log(f"[+] Compiler found: {cxx}", "info")
                return cc, cxx
        return None, None

    def install_gcc_temp(self):
        self.log("[*] Installing GCC locally in temp/", "info")
        os.makedirs(TEMP_DIR, exist_ok=True)
        os.chdir(TEMP_DIR)

        gcc_url = "http://ftp.gnu.org/gnu/gcc/gcc-13.2.0/gcc-13.2.0.tar.gz"
        self.run(f"curl -LO {gcc_url}")
        self.run("tar -xzf gcc-13.2.0.tar.gz")
        os.chdir("gcc-13.2.0")
        self.run("./contrib/download_prerequisites")
        os.makedirs("build", exist_ok=True)
        os.chdir("build")
        prefix = os.path.abspath("../gcc-install")
        self.run(f"../configure --prefix={prefix} --disable-multilib")
        self.run("make -j4")
        self.run("make install")

        gcc_bin = os.path.abspath("../gcc-install/bin")
        os.environ["PATH"] = gcc_bin + os.pathsep + os.environ["PATH"]
        os.environ["CC"] = os.path.join(gcc_bin, "gcc")
        os.environ["CXX"] = os.path.join(gcc_bin, "g++")
        os.chdir("../../../")
        return "gcc", "g++"

    def configure_cmake(self):
        os.makedirs(BUILD_DIR, exist_ok=True)
        build_path = os.path.abspath(BUILD_DIR)
        source_path = os.path.abspath(REPO_DIR)
        os.chdir(BUILD_DIR)

        cmd = ["cmake", source_path] + CMAKE_FLAGS
        if self.float128:
            cmd.append("-DFLOAT128=ON")
        if self.cc:
            cmd.append(f"-DCMAKE_C_COMPILER={self.cc}")
        if self.cxx:
            cmd.append(f"-DCMAKE_CXX_COMPILER={self.cxx}")
        self.run(" ".join(cmd))
        os.chdir("..")

    def build_project(self):
        os.chdir(BUILD_DIR)
        self.run("cmake --build . -j4")
        os.chdir("..")

    def clean_temp(self):
        if os.path.exists(TEMP_DIR):
            self.log("[*] Cleaning temporary GCC files", "info")
            shutil.rmtree(TEMP_DIR)

    def start_build(self):
        try:
            self.install_curl()
            self.clone_repo()
            self.cc, self.cxx = self.detect_compiler()

            if not self.cc:
                self.cc, self.cxx = self.install_gcc_temp()
                self.float128 = True
            elif self.cc == "gcc":
                self.float128 = True

            self.configure_cmake()
            self.build_project()
            self.clean_temp()
            self.log("\nOK: Wyland built successfully!", "success")
            # Removed enabling of move button
        except subprocess.CalledProcessError as e:
            self.log(f"[ERROR] Command failed: {e}", "stderr")
        except Exception as e:
            self.log(f"[EXCEPTION] {e}", "stderr")

if __name__ == "__main__":
    BuilderApp().mainloop()
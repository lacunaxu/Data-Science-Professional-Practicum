import os
import time
import csv
import subprocess
import ctypes

# ----------- simple PGM(P2) read/write -----------

def read_pgm_p2(path):
    with open(path, "r") as f:
        magic = f.readline().strip()
        if magic != "P2":
            raise ValueError("Not P2 PGM")

        # skip comments
        line = f.readline()
        while line.startswith("#") or line.strip() == "":
            line = f.readline()

        w, h = map(int, line.split())
        maxv = int(f.readline().strip())

        vals = []
        for token in f.read().split():
            vals.append(int(token))

    # normalize to 0..255
    if maxv != 255:
        vals = [int(v * 255.0 / maxv) for v in vals]
    vals = [0 if v < 0 else 255 if v > 255 else v for v in vals]

    if w != h:
        raise ValueError("Need square MxM")
    M = w
    return M, vals

def write_pgm_p2(path, M, vals):
    with open(path, "w") as f:
        f.write("P2\n")
        f.write(f"{M} {M}\n")
        f.write("255\n")
        for i, v in enumerate(vals):
            f.write(str(int(v)))
            f.write("\n" if (i + 1) % M == 0 else " ")

# ----------- load shared library -----------

def load_lib():
    lib = ctypes.CDLL("./libconv.so")
    # int conv_pgm_u32(const uint32_t*, uint32_t*, int, int, int)
    lib.conv_pgm_u32.argtypes = [
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int
    ]
    lib.conv_pgm_u32.restype = ctypes.c_int
    return lib

FILTER_ID = {"blur": 0, "sharpen": 1, "laplacian": 2}

# ----------- benchmark helpers -----------

def run_exe(cmd_list):
    t0 = time.perf_counter()
    subprocess.run(cmd_list, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    t1 = time.perf_counter()
    return t1 - t0

def run_python_lib(lib, in_pgm, out_pgm, filt, N):
    M, vals = read_pgm_p2(in_pgm)

    n = M * M
    InArr = (ctypes.c_uint32 * n)(*vals)
    OutArr = (ctypes.c_uint32 * n)()

    t0 = time.perf_counter()
    ret = lib.conv_pgm_u32(InArr, OutArr, M, FILTER_ID[filt], N)
    t1 = time.perf_counter()
    if ret != 0:
        raise RuntimeError(f"lib conv failed ret={ret}")

    out_vals = list(OutArr)
    write_pgm_p2(out_pgm, M, out_vals)
    return t1 - t0

def main():
    os.makedirs("outputs_step3", exist_ok=True)

    # 你自己的 Step1/Step2 可执行文件
    CPU_EXE = "./conv_step1"
    CUDA_EXE = "./conv_step2"

    lib = load_lib()

    # 你要测的输入：同一张图做 3 个 M (256,512,1024) + 3 张图 = 9 个输入
    inputs = [
        "inputs/pic1_256.pgm", "inputs/pic1_512.pgm", "inputs/pic1_1024.pgm",
        "inputs/pic2_256.pgm", "inputs/pic2_512.pgm", "inputs/pic2_1024.pgm",
        "inputs/pic3_256.pgm", "inputs/pic3_512.pgm", "inputs/pic3_1024.pgm",
    ]

    filters = ["blur", "sharpen", "laplacian"]
    Ns = [3, 5, 7]

    rows = []
    for inp in inputs:
        for filt in filters:
            for N in Ns:
                base = os.path.splitext(os.path.basename(inp))[0]
                out_cpu  = f"outputs_step3/{base}_{filt}_N{N}_cpu.pgm"
                out_cuda = f"outputs_step3/{base}_{filt}_N{N}_cudaexe.pgm"
                out_py   = f"outputs_step3/{base}_{filt}_N{N}_pylib.pgm"

                # 1) C CPU exe
                t_cpu = run_exe([CPU_EXE, inp, out_cpu, filt, str(N)])

                # 2) CUDA exe
                t_cudaexe = run_exe([CUDA_EXE, inp, out_cuda, filt, str(N)])

                # 3) Python + shared lib (CUDA inside)
                t_pylib = run_python_lib(lib, inp, out_py, filt, N)

                rows.append([inp, filt, N, t_cpu, t_cudaexe, t_pylib])
                print(inp, filt, N, "cpu", t_cpu, "cudaexe", t_cudaexe, "pylib", t_pylib)

    # write csv
    with open("timings.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["input", "filter", "N", "time_cpu_exe_s", "time_cuda_exe_s", "time_python_lib_s"])
        w.writerows(rows)

    print("\nWrote timings.csv")

if __name__ == "__main__":
    main()

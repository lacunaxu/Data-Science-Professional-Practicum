// conv_step2.cu
// Step 2: CUDA version of your Step 1 convolution (replicate boundary)
// Build on CUDA machine:
//   nvcc -O2 conv_step2.cu -o conv_step2
//
// Run:
//   ./conv_step2 in.pgm out.pgm blur 3
//   ./conv_step2 in.pgm out.pgm sharpen 5
//   ./conv_step2 in.pgm out.pgm laplacian 7

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <cuda_runtime.h>

/* ---------------- same helpers ---------------- */

static int clamp_int(int v, int lo, int hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static uint32_t clamp_0_255_int32(int v) {
    if (v < 0) return 0u;
    if (v > 255) return 255u;
    return (uint32_t)v;
}

/* PGM P2 (ASCII) reader: supports whitespace + multiple comment lines */
static int read_pgm_p2(const char* path, uint32_t** img, int* w, int* h) {
    FILE* f = fopen(path, "r");
    if (!f) return 0;

    char magic[3] = {0};
    if (fscanf(f, "%2s", magic) != 1) { fclose(f); return 0; }
    if (strcmp(magic, "P2") != 0) { fclose(f); return 0; }

    // skip comments anywhere
    int c = fgetc(f);
    while (c == ' ' || c == '\n' || c == '\r' || c == '\t') c = fgetc(f);
    while (c == '#') {
        while (c != '\n' && c != EOF) c = fgetc(f);
        c = fgetc(f);
        while (c == ' ' || c == '\n' || c == '\r' || c == '\t') c = fgetc(f);
    }
    ungetc(c, f);

    int maxv = 0;
    if (fscanf(f, "%d %d %d", w, h, &maxv) != 3) { fclose(f); return 0; }
    if (*w <= 0 || *h <= 0 || maxv <= 0) { fclose(f); return 0; }

    int n = (*w) * (*h);
    *img = (uint32_t*)malloc((size_t)n * sizeof(uint32_t));
    if (!*img) { fclose(f); return 0; }

    for (int i = 0; i < n; i++) {
        int v;
        if (fscanf(f, "%d", &v) != 1) { free(*img); fclose(f); return 0; }
        if (v < 0) v = 0;
        if (v > maxv) v = maxv;
        if (maxv != 255) v = (int)((double)v * 255.0 / (double)maxv);
        if (v < 0) v = 0;
        if (v > 255) v = 255;
        (*img)[i] = (uint32_t)v;
    }

    fclose(f);
    return 1;
}

static int write_pgm_p2(const char* path, const uint32_t* img, int w, int h) {
    FILE* f = fopen(path, "w");
    if (!f) return 0;

    fprintf(f, "P2\n%d %d\n255\n", w, h);
    for (int i = 0; i < w * h; i++) {
        fprintf(f, "%u%s", img[i], ((i + 1) % w == 0) ? "\n" : " ");
    }
    fclose(f);
    return 1;
}

/* ----- build kernel (same as yours) ----- */
static void build_kernel(const char* name, int N, int32_t* K, int32_t* scale) {
    for (int i = 0; i < N * N; i++) K[i] = 0;
    *scale = 1;

    if (strcmp(name, "blur") == 0) {
        for (int i = 0; i < N * N; i++) K[i] = 1;
        *scale = N * N;
        return;
    }

    int r = N / 2;

    if (strcmp(name, "laplacian") == 0) {
        K[r*N + r] = 4;
        K[(r-1)*N + r] = -1;
        K[(r+1)*N + r] = -1;
        K[r*N + (r-1)] = -1;
        K[r*N + (r+1)] = -1;
        return;
    }

    if (strcmp(name, "sharpen") == 0) {
        K[r*N + r] = 5;
        K[(r-1)*N + r] = -1;
        K[(r+1)*N + r] = -1;
        K[r*N + (r-1)] = -1;
        K[r*N + (r+1)] = -1;
        return;
    }

    printf("Unknown filter: %s\n", name);
    exit(1);
}

/* ---------------- CUDA conv kernel ---------------- */

__global__ void conv2d_replicate_kernel(
    const uint32_t* in, int M,
    const int32_t* K, int N,
    int32_t scale,
    int32_t* raw_out   // store raw as int32
) {
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    if (x >= M || y >= M) return;

    int r = N / 2;
    int32_t sum = 0;

    for (int ky = 0; ky < N; ky++) {
        int yy = y + ky - r;
        if (yy < 0) yy = 0;
        if (yy >= M) yy = M - 1;

        for (int kx = 0; kx < N; kx++) {
            int xx = x + kx - r;
            if (xx < 0) xx = 0;
            if (xx >= M) xx = M - 1;

            uint32_t pix = in[yy * M + xx];
            int32_t w = K[ky * N + kx];
            sum += (int32_t)pix * w;
        }
    }

    if (scale == 0) scale = 1;
    raw_out[y * M + x] = sum / scale;
}

/* raw(int32) -> u8 for output */
static void raw_to_u8_from_i32(const int32_t* raw, uint32_t* out, int n) {
    for (int i = 0; i < n; i++) out[i] = clamp_0_255_int32(raw[i]);
}

/* ---------------- main ---------------- */

int main(int argc, char** argv) {
    if (argc < 5) {
        printf("Usage: ./conv_step2 in.pgm out.pgm <blur|sharpen|laplacian> <N>\n");
        return 1;
    }

    const char* in_path = argv[1];
    const char* out_path = argv[2];
    const char* filter = argv[3];
    int N = atoi(argv[4]);

    uint32_t* img = NULL;
    int w = 0, h = 0;

    if (!read_pgm_p2(in_path, &img, &w, &h)) {
        printf("Read failed: %s\n", in_path);
        return 1;
    }
    if (w != h) {
        printf("Need square image (MxM). Got %dx%d\n", w, h);
        free(img);
        return 1;
    }

    int M = w;
    int n_pix = M * M;

    // host buffers
    uint32_t* out_u8 = (uint32_t*)malloc((size_t)n_pix * sizeof(uint32_t));
    int32_t* K_host = (int32_t*)malloc((size_t)N * (size_t)N * sizeof(int32_t));
    if (!out_u8 || !K_host) {
        printf("malloc failed.\n");
        free(img); free(out_u8); free(K_host);
        return 1;
    }

    int32_t scale = 1;
    build_kernel(filter, N, K_host, &scale);

    // device buffers
    uint32_t *d_in = NULL;
    int32_t  *d_K = NULL;
    int32_t  *d_raw = NULL;

    cudaMalloc((void**)&d_in,  (size_t)n_pix * sizeof(uint32_t));
    cudaMalloc((void**)&d_K,   (size_t)N * (size_t)N * sizeof(int32_t));
    cudaMalloc((void**)&d_raw, (size_t)n_pix * sizeof(int32_t));

    cudaMemcpy(d_in, img, (size_t)n_pix * sizeof(uint32_t), cudaMemcpyHostToDevice);
    cudaMemcpy(d_K,  K_host, (size_t)N * (size_t)N * sizeof(int32_t), cudaMemcpyHostToDevice);

    // launch
    dim3 block(16, 16);
    dim3 grid((M + block.x - 1) / block.x, (M + block.y - 1) / block.y);

    cudaEvent_t start, stop;
    cudaEventCreate(&start);
    cudaEventCreate(&stop);

    cudaEventRecord(start);
    conv2d_replicate_kernel<<<grid, block>>>(d_in, M, d_K, N, scale, d_raw);
    cudaEventRecord(stop);

    cudaEventSynchronize(stop);
    float ms = 0.0f;
    cudaEventElapsedTime(&ms, start, stop);

    // copy raw back + write output
    int32_t* raw_host = (int32_t*)malloc((size_t)n_pix * sizeof(int32_t));
    cudaMemcpy(raw_host, d_raw, (size_t)n_pix * sizeof(int32_t), cudaMemcpyDeviceToHost);

    raw_to_u8_from_i32(raw_host, out_u8, n_pix);
    write_pgm_p2(out_path, out_u8, M, M);

    printf("Done CUDA. M=%d, N=%d, filter=%s, kernel_time=%.6f sec\n", M, N, filter, (double)ms / 1000.0);

    // cleanup
    free(img);
    free(out_u8);
    free(K_host);
    free(raw_host);

    cudaFree(d_in);
    cudaFree(d_K);
    cudaFree(d_raw);

    cudaEventDestroy(start);
    cudaEventDestroy(stop);

    return 0;
}

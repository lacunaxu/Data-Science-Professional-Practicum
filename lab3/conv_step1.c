#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static int clamp_int(int v, int lo, int hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static uint32_t clamp_0_255(int64_t v) {
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

    /* skip comments anywhere */
    int c;
    c = fgetc(f);
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
        (*img)[i] = clamp_0_255((int64_t)v);
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

static void conv2d_raw_replicate(
    const uint32_t* in, int M,
    const int32_t* K, int N,
    int32_t scale,
    int64_t* raw_out
) {
    int r = N / 2;
    if (scale == 0) scale = 1;

    for (int y = 0; y < M; y++) {
        for (int x = 0; x < M; x++) {
            int64_t sum = 0;

            for (int ky = 0; ky < N; ky++) {
                int yy = clamp_int(y + ky - r, 0, M - 1);
                for (int kx = 0; kx < N; kx++) {
                    int xx = clamp_int(x + kx - r, 0, M - 1);
                    sum += (int64_t)in[yy * M + xx] * (int64_t)K[ky * N + kx];
                }
            }

            raw_out[y * M + x] = sum / (int64_t)scale;
        }
    }
}

static void raw_to_u8(const int64_t* raw, uint32_t* out, int n) {
    for (int i = 0; i < n; i++) out[i] = clamp_0_255(raw[i]);
}

int main(int argc, char** argv) {
    if (argc < 5) {
        printf("Usage: ./conv_step1 in.pgm out.pgm <blur|sharpen|laplacian> <N>\n");
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

    int64_t* raw = (int64_t*)malloc((size_t)n_pix * sizeof(int64_t));
    uint32_t* out_u8 = (uint32_t*)malloc((size_t)n_pix * sizeof(uint32_t));
    int32_t* K = (int32_t*)malloc((size_t)N * (size_t)N * sizeof(int32_t));

    int32_t scale = 1;
    build_kernel(filter, N, K, &scale);

    struct timespec a, b;
    clock_gettime(CLOCK_MONOTONIC, &a);

    conv2d_raw_replicate(img, M, K, N, scale, raw);

    clock_gettime(CLOCK_MONOTONIC, &b);
    double t = (b.tv_sec - a.tv_sec) + (b.tv_nsec - a.tv_nsec) * 1e-9;

    raw_to_u8(raw, out_u8, n_pix);
    write_pgm_p2(out_path, out_u8, M, M);

    printf("Done. M=%d, N=%d, filter=%s, time=%.6f sec\n", M, N, filter, t);

    free(img);
    free(raw);
    free(out_u8);
    free(K);
    return 0;
}

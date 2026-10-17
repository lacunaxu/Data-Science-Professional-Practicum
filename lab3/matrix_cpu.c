#include <stdio.h>
#include <stdlib.h>
#include <time.h>

void matrixMultiplyCPU(float *A, float *B, float *C, int N) {
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            float sum = 0.0f;
            for (int k = 0; k < N; k++) {
                sum += A[i * N + k] * B[k * N + j];
            }
            C[i * N + j] = sum;
        }
    }
}

int main(int argc, char **argv) {
    int N = (argc > 1) ? atoi(argv[1]) : 1024; // allow matrix size as input
    if (N <= 0) {
        printf("N must be positive.\n");
        return 1;
    }

    size_t size = (size_t)N * (size_t)N * sizeof(float);

    float *A = (float *)malloc(size);
    float *B = (float *)malloc(size);
    float *C = (float *)malloc(size);

    if (A == NULL || B == NULL || C == NULL) {
        printf("malloc failed.\n");
        free(A); free(B); free(C);
        return 1;
    }

    for (int i = 0; i < N * N; i++) {
        A[i] = rand() % 100 / 100.0f;
        B[i] = rand() % 100 / 100.0f;
    }

    clock_t start = clock();
    matrixMultiplyCPU(A, B, C, N);
    clock_t end = clock();

    double checksum = 0.0;
    for (int i = 0; i < N * N; i += (N * N / 10 + 1)) {
        checksum += C[i];
    }

    double elapsed = (double)(end - start) / CLOCKS_PER_SEC;
    printf("CPU execution time (N=%d): %f seconds\n", N, elapsed);
    printf("checksum: %.6f\n", checksum);


    free(A); free(B); free(C);
    return 0;
}

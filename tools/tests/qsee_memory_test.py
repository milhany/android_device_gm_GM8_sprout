#!/usr/bin/env python3
"""Fault-inject the actual unpublished QSEE listener ION setup function."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from qsee_wait_test import function


HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t ion_phys_addr_t;
typedef uint64_t phys_addr_t;
struct ion_handle { int unused; };
struct qseecom_dev_handle { int unused; };
struct qseecom_register_listener_req { int ifd_data_fd; };
struct qseecom_registered_listener_list {
    struct { uint32_t listener_id; } svc;
    struct ion_handle *ihandle;
    size_t sb_length;
    void *sb_virt;
    phys_addr_t sb_phys;
};
struct __attribute__((packed)) qseecom_register_listener_ireq {
    uint32_t qsee_cmd_id, listener_id, sb_ptr, sb_len;
};
struct __attribute__((packed)) qseecom_register_listener_64bit_ireq {
    uint32_t qsee_cmd_id, listener_id;
    uint64_t sb_ptr;
    uint32_t sb_len;
};
struct qseecom_command_scm_resp { uint32_t result, resp_type, data; };
static struct { void *ion_clnt; unsigned int qsee_version; } qseecom;
static struct ion_handle handle;
static char mapping[64];
static int fault, imports, maps, free_count, unmap_count, calls;
#define QSEE_VERSION_40 0x1000000
#define QSEOS_REGISTER_LISTENER 1
#define QSEOS_RESULT_SUCCESS 0
#define QSEOS_RESULT_INCOMPLETE 1
#define SCM_SVC_TZSCHEDULER 1
#define pr_err(...) ((void)0)
#define IS_ERR_OR_NULL(p) (!(p) || (uintptr_t)(p) >= (uintptr_t)-4095)
static struct ion_handle *ion_import_dma_buf(void *client, int fd) {
    if (fault == 1) return (struct ion_handle *)(intptr_t)-ENOMEM;
    if (fault == 6) return NULL;
    assert(!imports); imports++; return &handle;
}
static int ion_phys(void *client, struct ion_handle *h, ion_phys_addr_t *p, size_t *len) {
    assert(h == &handle && imports == 1);
    if (fault == 2) return -EINVAL;
    *p = UINT64_C(0x12345000); *len = sizeof(mapping); return 0;
}
static void *ion_map_kernel(void *client, struct ion_handle *h) {
    assert(h == &handle && imports == 1);
    if (fault == 3) return (void *)(intptr_t)-ENOMEM;
    if (fault == 7) return NULL;
    assert(!maps); maps++; return mapping;
}
static void ion_unmap_kernel(void *client, struct ion_handle *h) {
    assert(h == &handle && imports == 1 && maps == 1);
    maps--; unmap_count++;
}
static void ion_free(void *client, struct ion_handle *h) {
    assert(h == &handle && imports == 1 && !maps);
    imports--; free_count++;
}
static int qseecom_scm_call(uint32_t svc, uint32_t cmd, const void *buf,
                          size_t len, void *out, size_t outlen) {
    const struct qseecom_register_listener_ireq *r = buf;
    struct qseecom_command_scm_resp *resp = out;
    assert(imports == 1 && maps == 1 && outlen == sizeof(*resp));
    assert(r->qsee_cmd_id == QSEOS_REGISTER_LISTENER && r->listener_id == 0x2000);
    if (qseecom.qsee_version < QSEE_VERSION_40) {
        assert(len == sizeof(*r) && r->sb_ptr == 0x12345000 && r->sb_len == sizeof(mapping));
    } else {
        const struct qseecom_register_listener_64bit_ireq *r64 = buf;
        assert(len == sizeof(*r64) && r64->sb_ptr == 0x12345000 && r64->sb_len == sizeof(mapping));
    }
    calls++;
    if (fault == 4) return -EIO;
    resp->result = fault == 5 ? 0xffffffffU : QSEOS_RESULT_SUCCESS;
    return 0;
}
#include "actual.c"
int main(void) {
    int modern, stage, repeat, index;
    struct qseecom_registered_listener_list listener;
    struct qseecom_dev_handle data;
    struct qseecom_register_listener_req req;
    memset(&req, 0, sizeof(req)); req.ifd_data_fd = 3;
    for (modern = 0; modern < 2; modern++) {
        qseecom.qsee_version = modern ? QSEE_VERSION_40 : 0;
        for (repeat = 0; repeat < 30; repeat++) for (index = 0; index <= 7; index++) {
            int ret;
            stage = (index + 2) % 8;
            memset(&listener, 0, sizeof(listener)); listener.svc.listener_id = 0x2000;
            fault = stage; free_count = unmap_count = calls = 0;
            ret = __qseecom_set_sb_memory(&listener, &data, &req);
            if (stage) {
                assert(ret == (stage == 2 ? -EINVAL : stage == 5 ? -EPERM : stage == 4 ? -EINVAL : -ENOMEM));
                assert(!imports && !maps);
                assert(!listener.ihandle && !listener.sb_virt);
                assert(free_count == (stage == 1 || stage == 6 ? 0 : 1));
                assert(unmap_count == (stage == 4 || stage == 5 ? 1 : 0));
            } else {
                assert(ret == 0 && imports == 1 && maps == 1 && calls == 1);
                assert(!free_count && !unmap_count);
                assert(listener.ihandle == &handle && listener.sb_virt == mapping);
                ion_unmap_kernel(NULL, listener.ihandle); ion_free(NULL, listener.ihandle);
            }
        }
    }
    puts("PASS: actual ION listener setup; import/phys/map/SCM/TZ failures; exact 32/64-bit registration ABI; 480 balanced allocation attempts");
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    actual = function(args.source.read_text(), '__qseecom_set_sb_memory')
    with tempfile.TemporaryDirectory(prefix='gm8-qsee-memory-') as tmp:
        tmp = Path(tmp)
        (tmp / 'actual.c').write_text(actual + '\n')
        (tmp / 'host.c').write_text(HARNESS)
        cmd = ['cc', '-std=gnu89', '-Wall', '-Wextra', '-Werror',
               '-Wno-unused-parameter', '-g', '-O1', '-I', str(tmp)]
        if args.sanitize:
            cmd += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie']
        binary = tmp / 'test'
        subprocess.run(cmd + [str(tmp / 'host.c'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=10, env=dict(os.environ))


if __name__ == '__main__':
    main()

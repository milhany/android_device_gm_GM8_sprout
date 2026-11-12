/* Host shims for the selected, unmodified function bodies in actual.c.
 * This checks C control flow and close/wait ordering, not secure firmware.
 */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

typedef int bool;
#define true 1
#define false 0
typedef struct { int value; } atomic_t;
#define atomic_set(a, v) __atomic_store_n(&(a)->value, (v), __ATOMIC_SEQ_CST)
#define atomic_read(a) __atomic_load_n(&(a)->value, __ATOMIC_SEQ_CST)
#define SET(a, v) __atomic_store_n(&(a), (v), __ATOMIC_SEQ_CST)
#define GET(a) __atomic_load_n(&(a), __ATOMIC_SEQ_CST)

struct list_head { struct list_head *next, *prev; };
#define container_of(p, type, member) ((type *)((char *)(p) - offsetof(type, member)))
#define list_entry(p, type, member) container_of(p, type, member)
#define list_for_each_entry(pos, head, member) \
    for (pos = list_entry((head)->next, __typeof__(*pos), member); \
         &pos->member != (head); \
         pos = list_entry(pos->member.next, __typeof__(*pos), member))
static void list_init(struct list_head *h) { h->next = h; h->prev = h; }
static void list_add_tail(struct list_head *n, struct list_head *h) {
    n->prev = h->prev; n->next = h; h->prev->next = n; h->prev = n;
}
static void list_del(struct list_head *n) { n->next->prev = n->prev; n->prev->next = n->next; }

typedef pthread_cond_t wait_queue_head_t;
static pthread_mutex_t app_access_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t qsee_bw_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t wait_lock = PTHREAD_MUTEX_INITIALIZER;
#define mutex_lock(p) assert(!pthread_mutex_lock(p))
#define mutex_unlock(p) assert(!pthread_mutex_unlock(p))
#define spin_lock_irqsave(p, flags) do { (flags) = 0; mutex_lock(p); } while (0)
#define spin_unlock_irqrestore(p, flags) do { (void)(flags); mutex_unlock(p); } while (0)
#define init_waitqueue_head(p) assert(!pthread_cond_init(p, NULL))
static int waiting, client_done, close_done, failure_responses, success_responses;
static int seq, response_seq, dereg_seq, unmap_seq, cache_calls;
static int scm_error, dereg_error, response_seen_closed_buffer;
static int next_listener, chain_step;
static void wake_up_all(wait_queue_head_t *q) {
    mutex_lock(&wait_lock); assert(!pthread_cond_broadcast(q)); mutex_unlock(&wait_lock);
}
#define wake_up_interruptible wake_up_all
#define wait_event_freezable(q, condition) ({ \
    mutex_lock(&wait_lock); \
    while (!(condition)) { SET(waiting, 1); assert(!pthread_cond_wait(&(q), &wait_lock)); } \
    mutex_unlock(&wait_lock); 0; })

/* Keep POSIX signal handling out of the host test: real kernel signal mask
 * calls are retained verbatim in actual.c and mapped to no-op host shims. */
#define sigfillset(p) ((void)(p))
#define sigprocmask(how, set, old) ((void)(set), (void)(old))
#define SIG_SETMASK 2
#define pr_err(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_debug(...) ((void)0)
#define ERESTARTSYS 512
#define MAX_ION_FD 4
#define SGLISTINFO_TABLE_SIZE (sizeof(struct sglist_info) * MAX_ION_FD)
#define QSEE_VERSION_40 0x1000000
#define QSEOS_RESULT_SUCCESS 0
#define QSEOS_RESULT_INCOMPLETE 1
#define QSEOS_RESULT_FAILURE 0xffffffffU
#define QSEOS_LISTENER_DATA_RSP_COMMAND 0x07
#define QSEOS_LISTENER_DATA_RSP_COMMAND_WHITELIST 0x1f
#define QSEOS_DEREGISTER_LISTENER 0x05
#define RPMB_SERVICE 0x2000
#define SSD_SERVICE 0x3000
#define CLK_QSEE 0
#define CLK_DFAB 1
#define CLK_SFPB 2
#define INACTIVE 0
#define SCM_SVC_TZSCHEDULER 1
#define ION_IOC_CLEAN_INV_CACHES 0
#define IS_ERR_OR_NULL(p) (!(p))
#define PF_EXITING 4
#define SIGNAL_GROUP_EXIT 4
#define GFP_KERNEL 0
#define VERIFY_WRITE 0
#define __user
struct pid { int number, references; };
struct signal_struct { int flags; };
struct task_struct { unsigned long flags; struct signal_struct *signal; struct pid *tgid; };
static struct pid owner_a = {77, 0}, owner_b = {77, 0}; /* Same number, distinct identity. */
static struct signal_struct owner_signal;
static __thread struct task_struct host_current;
#define current (&host_current)
static struct pid *task_tgid(struct task_struct *t) { return t->tgid; }
static struct pid *get_pid(struct pid *p) {
    if (p) __atomic_add_fetch(&p->references, 1, __ATOMIC_SEQ_CST);
    return p;
}
static void put_pid(struct pid *p) {
    if (p) assert(__atomic_sub_fetch(&p->references, 1, __ATOMIC_SEQ_CST) >= 0);
}
struct sglist_info { uint32_t a, b; };
struct ion_handle { int alive; };
struct __attribute__((packed)) qseecom_register_listener_ireq {
    uint32_t qsee_cmd_id, listener_id, sb_ptr, sb_len;
};
struct __attribute__((packed)) qseecom_command_scm_resp { uint32_t result, resp_type, data; };
struct __attribute__((packed)) qseecom_client_listener_data_irsp {
    uint32_t qsee_cmd_id, listener_id, status, sglistinfo_ptr, sglistinfo_len;
};
struct __attribute__((packed)) qseecom_client_listener_data_64bit_irsp {
    uint32_t qsee_cmd_id, listener_id, status;
    uint64_t sglistinfo_ptr;
    uint32_t sglistinfo_len;
};
struct qseecom_register_listener_req {
    uint32_t listener_id, sb_size;
    void *virt_sb_base;
};
struct qseecom_registered_listener_list {
    struct list_head list;
    struct qseecom_register_listener_req svc;
    struct ion_handle *ihandle;
    void *sb_virt;
    size_t sb_length;
    void *user_virt_sb_base;
    wait_queue_head_t rcv_req_wq;
    wait_queue_head_t listener_block_app_wq;
    volatile int rcv_req_flag, send_resp_flag;
    atomic_t legacy_close;
    struct pid *owner_tgid;
    bool listener_in_use;
    struct sglist_info sglistinfo_ptr[MAX_ION_FD];
    uint32_t sglist_cnt;
};
enum { QSEECOM_CLIENT_APP = 1, QSEECOM_LISTENER_SERVICE,
       QSEECOM_SECURE_SERVICE, QSEECOM_GENERIC, QSEECOM_UNAVAILABLE_CLIENT_APP };
struct qseecom_dev_handle {
    int type;
    struct { uint32_t id; } listener;
    struct { uint32_t app_id; } client;
    bool released;
    volatile int abort;
    atomic_t ioctl_count;
    wait_queue_head_t abort_wq;
    int mode;
    bool fast_load_enabled, perf_enabled;
};
struct inode { int unused; };
struct file { void *private_data; };
static struct {
    struct list_head registered_listener_list_head;
    pthread_mutex_t registered_listener_list_lock;
    wait_queue_head_t send_resp_wq;
    volatile int send_resp_flag;
    int qsee_reentrancy_support, qsee_version, whitelist_support;
    int support_bus_scaling, cumulative_mode;
    void *ion_clnt;
} qseecom;
static struct ion_handle buffer_handle;
static struct qseecom_dev_handle client;
static int client_result;

static int msm_ion_do_cache_op(void *a, struct ion_handle *h, void *v, size_t len, int op) {
    assert(h->alive); cache_calls++; return 0;
}
static void ion_unmap_kernel(void *a, struct ion_handle *h) {
    assert(h->alive); h->alive = 0; unmap_seq = ++seq;
}
static void ion_free(void *a, struct ion_handle *h) { assert(!h->alive); }
static int allocation_count, copy_error, access_error, alloc_error, sb_error;
static void *kzalloc(size_t size, int flags) {
    void *p;
    if (alloc_error) return NULL;
    p = calloc(1, size);
    if (p) allocation_count++;
    return p;
}
static void kzfree(struct qseecom_registered_listener_list *p) {
    if (!p) return;
    if (p->owner_tgid) {
        pthread_cond_destroy(&p->rcv_req_wq);
        pthread_cond_destroy(&p->listener_block_app_wq);
    }
    allocation_count--;
    free(p);
}
static int copy_from_user(void *out, const void *in, size_t size) {
    if (copy_error) return 1;
    memcpy(out, in, size); return 0;
}
static int access_ok(int kind, void *ptr, size_t size) { return !access_error; }
static int __qseecom_is_svc_unique(struct qseecom_dev_handle *d,
                                  struct qseecom_register_listener_req *req) {
    struct qseecom_registered_listener_list *p;
    list_for_each_entry(p, &qseecom.registered_listener_list_head, list)
        if (p->svc.listener_id == req->listener_id) return 0;
    return 1;
}
static int __qseecom_set_sb_memory(struct qseecom_registered_listener_list *p,
                                  struct qseecom_dev_handle *d,
                                  struct qseecom_register_listener_req *req) {
    if (sb_error) return -EIO;
    p->ihandle = &buffer_handle; p->sb_virt = p; return 0;
}
#define kfree(p) free(p)
#define virt_to_phys(p) ((uintptr_t)(p))
#define dmac_flush_range(a,b) ((void)0)
static int __qseecom_enable_clk(int c) { return 0; }
static int __qseecom_disable_clk(int c) { return 0; }
static int qseecom_unload_app(struct qseecom_dev_handle *d, bool c) { return 0; }
static int qseecom_unmap_ion_allocated_memory(struct qseecom_dev_handle *d) { return 0; }
static int qseecom_unregister_bus_bandwidth_needs(struct qseecom_dev_handle *d) { return 0; }
static int __qseecom_set_msm_bus_request(int mode) { return 0; }
static int qsee_disable_clock_vote(struct qseecom_dev_handle *d, int c) { return 0; }
static int __qseecom_qseos_fail_return_resp_tz(struct qseecom_dev_handle *d,
    struct qseecom_command_scm_resp *r, struct qseecom_client_listener_data_irsp *x,
    struct qseecom_registered_listener_list *l, uint32_t id) { return -EINVAL; }

static int qseecom_scm_call(uint32_t svc, uint32_t cmd, const void *buf,
    size_t len, void *out, size_t outlen) {
    const struct qseecom_client_listener_data_irsp *r = buf;
    struct qseecom_command_scm_resp *resp = out;
    if (r->qsee_cmd_id == QSEOS_DEREGISTER_LISTENER) {
        assert(len == sizeof(struct qseecom_register_listener_ireq));
        dereg_seq = ++seq;
        if (dereg_error) return dereg_error;
        resp->result = QSEOS_RESULT_SUCCESS;
        return 0;
    }
    assert(r->qsee_cmd_id == QSEOS_LISTENER_DATA_RSP_COMMAND ||
           r->qsee_cmd_id == QSEOS_LISTENER_DATA_RSP_COMMAND_WHITELIST);
    assert(len == (qseecom.qsee_version < QSEE_VERSION_40 ?
        sizeof(struct qseecom_client_listener_data_irsp) :
        sizeof(struct qseecom_client_listener_data_64bit_irsp)));
    assert(buffer_handle.alive);
    response_seen_closed_buffer = !buffer_handle.alive;
    response_seq = ++seq;
    if (r->status == QSEOS_RESULT_FAILURE) failure_responses++;
    else { assert(r->status == QSEOS_RESULT_SUCCESS); success_responses++; }
    if (scm_error) return scm_error;
    if (next_listener) {
        resp->result = QSEOS_RESULT_INCOMPLETE;
        resp->data = next_listener;
        next_listener = 0;
        SET(waiting, 0);
        SET(chain_step, 1);
    } else resp->result = QSEOS_RESULT_SUCCESS;
    return 0;
}

#include "actual.c"

static struct qseecom_registered_listener_list *add_listener(unsigned int id) {
    struct qseecom_dev_handle data;
    struct qseecom_register_listener_req req;
    struct qseecom_registered_listener_list *l;
    memset(&data, 0, sizeof(data)); memset(&req, 0, sizeof(req));
    req.listener_id = id; req.sb_size = sizeof(*l); req.virt_sb_base = &data;
    assert(qseecom_register_listener(&data, &req) == 0);
    l = list_entry(qseecom.registered_listener_list_head.prev,
                   struct qseecom_registered_listener_list, list);
#ifdef GROUP_BASELINE
    l->owner_tgid = get_pid(task_tgid(current));
#endif
    return l;
}
static struct qseecom_dev_handle *handle(unsigned int id) {
    struct qseecom_dev_handle *d = calloc(1, sizeof(*d));
    assert(d);
    d->type = QSEECOM_LISTENER_SERVICE;
    d->listener.id = id;
    init_waitqueue_head(&d->abort_wq);
    return d;
}
static void *run_client(void *unused) {
    struct qseecom_command_scm_resp resp = {QSEOS_RESULT_INCOMPLETE, 0, 0x2000};
    mutex_lock(&app_access_lock);
    client_result = __qseecom_process_incomplete_cmd(&client, &resp);
    mutex_unlock(&app_access_lock);
    SET(client_done, 1);
    return NULL;
}
static void *run_close(void *d) {
    struct file f;
    f.private_data = d;
    qseecom_release(NULL, &f);
    SET(close_done, 1);
    return NULL;
}
static void *run_group_close(void *d) {
    host_current.tgid = &owner_a;
    host_current.signal = &owner_signal;
    host_current.flags = PF_EXITING;
    return run_close(d);
}
static void await(int *flag) {
    unsigned int n;
    for (n = 0; n < 2000 && !GET(*flag); n++) usleep(1000);
    assert(GET(*flag));
}
static void reply(void) {
    SET(qseecom.send_resp_flag, 1);
    wake_up_all(&qseecom.send_resp_wq);
}
static void setup(int modern, int whitelist) {
    host_current.tgid = &owner_a; host_current.signal = &owner_signal;
    host_current.flags = 0; owner_signal.flags = 0;
    copy_error = access_error = alloc_error = sb_error = 0;
    list_init(&qseecom.registered_listener_list_head);
    qseecom.qsee_reentrancy_support = 0;
    qseecom.qsee_version = modern ? QSEE_VERSION_40 : 0;
    qseecom.whitelist_support = whitelist;
    SET(qseecom.send_resp_flag, 0);
    buffer_handle.alive = 1;
    memset(&client, 0, sizeof(client));
    client.client.app_id = 7;
    waiting = client_done = close_done = 0;
    failure_responses = success_responses = 0;
    seq = response_seq = dereg_seq = unmap_seq = cache_calls = 0;
    scm_error = dereg_error = response_seen_closed_buffer = 0;
    next_listener = chain_step = 0;
    client_result = 999;
}
static void free_list(void) {
    while (qseecom.registered_listener_list_head.next != &qseecom.registered_listener_list_head) {
        struct qseecom_registered_listener_list *l = list_entry(
            qseecom.registered_listener_list_head.next,
            struct qseecom_registered_listener_list, list);
        list_del(&l->list);
        put_pid(l->owner_tgid);
        kzfree(l);
    }
}
static void normal_case(int modern, int whitelist) {
    pthread_t a;
    setup(modern, whitelist); add_listener(0x2000);
    assert(!pthread_create(&a, NULL, run_client, NULL)); await(&waiting);
    assert(!GET(client_done)); reply(); assert(!pthread_join(a, NULL));
    assert(client_result == 0 && success_responses == 1 && failure_responses == 0);
    assert(buffer_handle.alive && cache_calls == 1);
    free_list();
}
static void close_case(int modern, int whitelist, int error, int response_first) {
    pthread_t a, b;
    setup(modern, whitelist); add_listener(0x2000); scm_error = error;
    if (response_first) SET(qseecom.send_resp_flag, 1);
    assert(!pthread_create(&a, NULL, run_client, NULL));
    if (!response_first) await(&waiting); else await(&client_done);
    assert(!pthread_create(&b, NULL, run_close, handle(0x2000)));
#ifdef BASELINE
    usleep(150000);
    assert(!GET(client_done) && !GET(close_done));
    puts("PASS: original C reproduces the close/wait deadlock; test-only reply releases it");
    reply();
#endif
    assert(!pthread_join(a, NULL)); assert(!pthread_join(b, NULL));
#ifdef BASELINE
    assert(client_result == 0);
#else
    if (response_first) assert(client_result == (error ? error : 0) && failure_responses == 0);
    else {
        assert(client_result == (error ? error : -ENODEV));
        assert(failure_responses == 1 && success_responses == 0);
    }
#endif
    assert(response_seq > 0 && dereg_seq > response_seq && unmap_seq > dereg_seq);
    assert(!buffer_handle.alive && !response_seen_closed_buffer);
    assert(qseecom.registered_listener_list_head.next == &qseecom.registered_listener_list_head);
}
#ifndef BASELINE
static void group_close_case(int modern, int whitelist, int chain, int error) {
    pthread_t a, b;
    struct qseecom_registered_listener_list *target, *foreign;
    setup(modern, whitelist);
    target = add_listener(0x2000); add_listener(0x3000);
    if (chain) { add_listener(0x4000); next_listener = 0x4000; }
    host_current.tgid = &owner_b; foreign = add_listener(0x5000);
    host_current.tgid = &owner_a;
    owner_signal.flags = SIGNAL_GROUP_EXIT; scm_error = error;
    assert(!pthread_create(&a, NULL, run_client, NULL)); await(&waiting);
    /* The first final close belongs to this dying group, but not the listener
     * the client is awaiting. The former fix cannot progress to the next FD. */
    assert(!pthread_create(&b, NULL, run_group_close, handle(0x3000)));
#ifdef GROUP_BASELINE
    usleep(150000);
    assert(!GET(client_done) && !GET(close_done));
    assert(!atomic_read(&target->legacy_close));
    reply(); /* Test rescue only: the dead listener group cannot actually reply. */
#endif
    assert(!pthread_join(a, NULL)); assert(!pthread_join(b, NULL));
#ifdef GROUP_BASELINE
    assert(client_result == 0 && !failure_responses);
    put_pid(&owner_a); /* The predecessor does not own this fixture-only ref. */
    puts("PASS: predecessor reproduces dying-group multi-listener deadlock; test reply rescues it");
#else
    assert(client_result == (error ? error : -ENODEV));
    assert(atomic_read(&target->legacy_close));
    assert(failure_responses == (chain && !error ? 2 : 1));
    assert(success_responses == 0);
    assert(dereg_seq > response_seq && unmap_seq > dereg_seq);
    assert(!response_seen_closed_buffer);
#endif
    /* Numeric TGID reuse cannot kill another service's identically numbered PID. */
    assert(!atomic_read(&foreign->legacy_close));
    free_list();
    assert(!owner_a.references && !owner_b.references && !allocation_count);
}
static void group_scope_case(void) {
    struct qseecom_registered_listener_list *target, *closing;
    struct qseecom_dev_handle *d;
    setup(0, 0); target = add_listener(0x2000); closing = add_listener(0x3000);
    d = handle(0x3000);
    host_current.flags = PF_EXITING; /* Exiting a single thread is insufficient. */
    __qseecom_abort_legacy_listener(d);
    assert(!atomic_read(&target->legacy_close) && atomic_read(&closing->legacy_close));
    atomic_set(&closing->legacy_close, 0); host_current.flags = 0;
    owner_signal.flags = SIGNAL_GROUP_EXIT; /* The closer must also be exiting. */
    __qseecom_abort_legacy_listener(d);
    assert(!atomic_read(&target->legacy_close) && atomic_read(&closing->legacy_close));
    atomic_set(&closing->legacy_close, 0); host_current.flags = PF_EXITING;
    host_current.tgid = &owner_b; /* Same numeric TGID, different stable identity. */
    __qseecom_abort_legacy_listener(d);
    assert(!atomic_read(&target->legacy_close) && atomic_read(&closing->legacy_close));
    atomic_set(&closing->legacy_close, 0); host_current.tgid = &owner_a;
    qseecom.qsee_reentrancy_support = 2;
    __qseecom_abort_legacy_listener(d);
    assert(!atomic_read(&target->legacy_close) && !atomic_read(&closing->legacy_close));
    free(d); free_list();
    assert(!owner_a.references && !owner_b.references && !allocation_count);
}
static void registration_lifetime_case(void) {
    struct qseecom_register_listener_req req;
    struct qseecom_dev_handle *d, duplicate;
    setup(0, 0); d = handle(0x2000);
    memset(&req, 0, sizeof(req)); req.listener_id = 0x2000;
    req.sb_size = 16; req.virt_sb_base = d;
    copy_error = 1; assert(qseecom_register_listener(d, &req) != 0); copy_error = 0;
    access_error = 1; assert(qseecom_register_listener(d, &req) == -EFAULT); access_error = 0;
    alloc_error = 1; assert(qseecom_register_listener(d, &req) == -ENOMEM); alloc_error = 0;
    sb_error = 1; assert(qseecom_register_listener(d, &req) == -ENOMEM); sb_error = 0;
    assert(!owner_a.references && !allocation_count);
    assert(qseecom_register_listener(d, &req) == 0);
    assert(owner_a.references == 1 && allocation_count == 1);
    memset(&duplicate, 0, sizeof(duplicate));
    assert(qseecom_register_listener(&duplicate, &req) == -EBUSY);
    assert(owner_a.references == 1 && allocation_count == 1);
    run_close(d);
    assert(!owner_a.references && !allocation_count);
}
static void unrelated_case(void) {
    pthread_t a, b;
    setup(0, 0); add_listener(0x2000); add_listener(0x3000);
    assert(!pthread_create(&a, NULL, run_client, NULL)); await(&waiting);
    assert(!pthread_create(&b, NULL, run_close, handle(0x3000)));
    usleep(30000);
    assert(!GET(client_done) && !GET(close_done) && !failure_responses);
    reply(); assert(!pthread_join(a, NULL)); assert(!pthread_join(b, NULL));
    assert(client_result == 0 && success_responses == 1 && failure_responses == 0);
    free_list();
}
static void early_close_case(void) {
    pthread_t a;
    struct qseecom_registered_listener_list *l;
    struct qseecom_dev_handle *d;
    setup(0, 0); l = add_listener(0x2000); d = handle(0x2000);
    __qseecom_abort_legacy_listener(d);
    assert(atomic_read(&l->legacy_close) == 1);
    assert(!pthread_create(&a, NULL, run_client, NULL)); assert(!pthread_join(a, NULL));
    assert(client_result == -ENODEV && failure_responses == 1 && buffer_handle.alive);
    run_close(d);
    assert(dereg_seq > response_seq && unmap_seq > dereg_seq);
}
static void reentrant_guard_case(void) {
    struct qseecom_registered_listener_list *l;
    struct qseecom_dev_handle *d;
    setup(0, 0); l = add_listener(0x2000); d = handle(0x2000);
    qseecom.qsee_reentrancy_support = 2;
    __qseecom_abort_legacy_listener(d);
    assert(atomic_read(&l->legacy_close) == 0 && buffer_handle.alive);
    assert(!__qseecom_listener_has_sent_rsp(&client, l));
    assert(!__qseecom_reentrancy_listener_has_sent_rsp(&client, l));
    free(d); free_list();
}
static void missing_listener_case(void) {
    struct qseecom_dev_handle *d;
    setup(0, 0); d = handle(0x2000);
    __qseecom_abort_legacy_listener(d);
    assert(!qseecom.send_resp_flag && buffer_handle.alive);
    free(d);
}
static void dereg_error_case(void) {
    struct qseecom_dev_handle *d;
    setup(0, 0); add_listener(0x2000); d = handle(0x2000);
    dereg_error = -EIO;
    run_close(d);
    assert(buffer_handle.alive && !unmap_seq);
    assert(qseecom.registered_listener_list_head.next != &qseecom.registered_listener_list_head);
    free_list();
}
static void chained_listener_case(void) {
    pthread_t a, b;
    setup(1, 1); add_listener(0x2000); add_listener(0x3000);
    next_listener = 0x3000;
    assert(!pthread_create(&a, NULL, run_client, NULL)); await(&waiting);
    assert(!pthread_create(&b, NULL, run_close, handle(0x2000)));
    await(&chain_step); await(&waiting);
    assert(!GET(client_done) && !GET(close_done) && buffer_handle.alive);
    reply(); assert(!pthread_join(a, NULL)); assert(!pthread_join(b, NULL));
    assert(client_result == -ENODEV && failure_responses == 1 && success_responses == 1);
    assert(dereg_seq > response_seq && unmap_seq > dereg_seq);
    free_list();
}
#endif
int main(void) {
#if !defined(BASELINE) && !defined(GROUP_BASELINE)
    int modern, whitelist, n;
#endif
    pthread_mutex_init(&qseecom.registered_listener_list_lock, NULL);
    init_waitqueue_head(&qseecom.send_resp_wq);
    assert(owner_a.number == owner_b.number);
#ifdef BASELINE
    close_case(0, 0, 0, 0);
#elif defined(GROUP_BASELINE)
    group_close_case(0, 0, 0, 0);
#else
    for (modern = 0; modern < 2; modern++) for (whitelist = 0; whitelist < 2; whitelist++) {
        normal_case(modern, whitelist);
        close_case(modern, whitelist, 0, 0);
        close_case(modern, whitelist, -EIO, 0);
        close_case(modern, whitelist, 0, 1);
    }
    unrelated_case(); early_close_case(); reentrant_guard_case();
    missing_listener_case(); dereg_error_case();
    chained_listener_case();
    for (modern = 0; modern < 2; modern++) for (whitelist = 0; whitelist < 2; whitelist++) {
        group_close_case(modern, whitelist, 0, 0);
        group_close_case(modern, whitelist, 1, 0);
        group_close_case(modern, whitelist, 0, -EIO);
    }
    group_scope_case(); registration_lifetime_case();
    for (n = 0; n < 100; n++) {
        close_case(n & 1, (n >> 1) & 1, 0, 0);
        group_close_case(n & 1, (n >> 1) & 1, n & 1, 0);
    }
    assert(!owner_a.references && !owner_b.references && !allocation_count);
    puts("PASS: actual C wait/close/unregister; normal response; failure and SCM error; unrelated listener; early close; reentrant guard; absent listener; deregister error; chained TZ response; 100 close races");
    puts("PASS: dying group with first unrelated FD; chained listener failures; foreign/reused TGID isolation; exit flags; registration PID lifetime and error paths; 100 group-close races");
#endif
    return 0;
}

#!/usr/bin/env python3
"""Exercise actual legacy RT admission and Android cgroup path resolution."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--top', type=Path, default=Path(__file__).resolve().parents[5])
parser.add_argument('--kernel-core', type=Path)
parser.add_argument('--cgroup-map', type=Path)
parser.add_argument('--defaults', type=Path)
parser.add_argument('--task-profiles-source', type=Path)
args = parser.parse_args()
device = Path(__file__).resolve().parents[2]
core = (args.kernel_core or args.top / 'kernel/gm/msm8937/kernel/sched/core.c').read_text()
controller = (args.cgroup_map or args.top / 'system/core/libprocessgroup/cgroup_map.cpp').read_text()
defaults = json.loads((args.defaults or args.top /
                      'system/core/libprocessgroup/profiles/task_profiles.json').read_text())
vendor = json.loads((device / 'configs/task-profiles-gm8.json').read_text())
profile_source = (args.task_profiles_source or args.top /
                  'system/core/libprocessgroup/task_profiles.cpp').read_text()
profile_methods = '\n'.join(function(profile_source, signature) for signature in (
    'void TaskProfile::MoveTo(', 'bool TaskProfile::ExecuteForProcess(',
    'bool TaskProfile::ExecuteForTask('))


# Use the real __sched_setscheduler zero-runtime permission branch, including
# its autogroup exemption, and the actual cgroup RT attachment check.
gate = function(core, 'if (rt_bandwidth_enabled() && rt_policy(policy) &&')
attach = function(core, 'static int sched_rt_can_attach(')
paths = '\n'.join(function(controller, signature) for signature in (
    'std::string CgroupController::GetTasksFilePath(',
    'std::string CgroupController::GetProcsFilePath('))

program = r'''
#include <cassert>
#include <cerrno>
#include <regex>
#include <string>
#include <sys/types.h>
#include <vector>
#include <memory>
struct task_group {struct {long rt_runtime;} rt_bandwidth;bool autogroup;};
struct task_struct {task_group* group;int policy;};
bool rt_policy(int policy) {return policy==1 || policy==2;}
bool rt_task(task_struct* task) {return rt_policy(task->policy);}
task_group* task_group_of(task_struct* task) {return task->group;}
#define task_group(task) task_group_of(task)
bool task_group_is_autogroup(struct task_group* group) {return group->autogroup;}
bool rt_bandwidth_enabled() {return true;}
void task_rq_unlock(int,task_struct*,int*) {}
int may_set_policy(task_struct* p,int policy) {
 int rq=0,flags=0;
GATE
 return 0;
}
ATTACH
static constexpr const char* CGROUP_TASKS_FILE="/tasks";
static constexpr const char* CGROUP_TASKS_FILE_V2="/cgroup.tasks";
static constexpr const char* CGROUP_PROCS_FILE="/cgroup.procs";
struct CgroupController {
 const char* path() const {return "/dev/cpuctl";}
 int version() const {return 1;}
 std::string GetTasksFilePath(const std::string&) const;
 std::string GetProcsFilePath(const std::string&,uid_t,pid_t) const;
};
PATHS
int memoryAttributeWrites=0;
struct ProfileAction {
 bool ExecuteForProcess(uid_t,pid_t) const {++memoryAttributeWrites;return true;}
 bool ExecuteForTask(int) const {++memoryAttributeWrites;return true;}
};
struct TaskProfile {
 std::vector<std::unique_ptr<ProfileAction>> elements_;
 bool res_cached_=false;
 void MoveTo(TaskProfile*);
 bool ExecuteForProcess(uid_t,pid_t) const;
 bool ExecuteForTask(int) const;
};
int GetThreadId() {return 123;}
PROFILE_METHODS
int main(int argc,char**argv) {
 assert(argc==2);
 // Actual vendor override semantics: an empty profile clears the original
 // shared-group attribute actions and remains a successful no-op.
 TaskProfile original,empty;
 original.elements_.push_back(std::make_unique<ProfileAction>());
 empty.MoveTo(&original);
 assert(original.elements_.empty());
 assert(original.ExecuteForProcess(1000,123));
 assert(original.ExecuteForTask(0));
 assert(memoryAttributeWrites==0);
 struct task_group root{{950000},false},child{{0},false},autogroup{{0},true};
 task_struct normal{&child,0},fifo{&child,1};
 // Reproduce both creating an RT timer thread and moving an existing RT task.
 assert(may_set_policy(&normal,1)==-EPERM);
 assert(may_set_policy(&normal,2)==-EPERM);
 assert(may_set_policy(&normal,0)==0);
 assert(!sched_rt_can_attach(&child,&fifo));
 assert(sched_rt_can_attach(&child,&normal));
 normal.group=&autogroup;assert(may_set_policy(&normal,1)==0);
 normal.group=&root;assert(may_set_policy(&normal,1)==0);
 assert(sched_rt_can_attach(&root,&fifo));
 CgroupController controller;
 assert(controller.GetTasksFilePath("top-app")=="/dev/cpuctl/top-app/tasks");
 assert(controller.GetTasksFilePath(argv[1])=="/dev/cpuctl/tasks");
 // libprocessgroup permits the redundant slash for a root process path.
 assert(controller.GetProcsFilePath(argv[1],1002,123)=="/dev/cpuctl//cgroup.procs");
}
'''.replace('GATE', gate).replace('ATTACH', attach).replace('PATHS', paths).replace('PROFILE_METHODS', profile_methods)

# Android merges vendor leaf profiles with system aggregate profiles. Verify
# that RT-safe CPU membership does not replace cpuset/IO/timer-slack actions.
merged = {p['Name']: p for p in defaults['Profiles']}
expected = {'HighEnergySaving', 'NormalPerformance', 'ServicePerformance',
            'HighPerformance', 'MaxPerformance', 'RealtimePerformance',
            'CameraServicePerformance', 'NNApiHALPerformance', 'Dex2oatPerformance'}
memory = {'LowMemoryUsage', 'HighMemoryUsage'}
assert {p['Name'] for p in vendor['Profiles']} == expected | memory
assert len(vendor['Profiles']) == len(expected | memory)
assert all(p['Actions'] == [] for p in vendor['Profiles'] if p['Name'] in memory)
cpu_profiles = [p for p in vendor['Profiles'] if p['Name'] in expected]
assert not vendor.get('AggregateProfiles')
for profile in cpu_profiles:
    assert profile['Actions'] == [{'Name': 'JoinCgroup', 'Params': {
        'Controller': 'cpu', 'Path': ''}}], profile['Name']
    merged[profile['Name']] = profile
aggregates = {p['Name']: p['Profiles'] for p in defaults['AggregateProfiles']}
for aggregate, capacity, io, slack in (
        ('CPUSET_SP_BACKGROUND', 'ProcessCapacityLow', 'LowIoPriority', 'TimerSlackHigh'),
        ('CPUSET_SP_FOREGROUND', 'ProcessCapacityHigh', 'HighIoPriority', 'TimerSlackNormal'),
        ('CPUSET_SP_TOP_APP', 'ProcessCapacityMax', 'MaxIoPriority', 'TimerSlackNormal')):
    members = aggregates[aggregate]
    assert capacity in members and io in members and slack in members
    assert any(a['Name'] == 'JoinCgroup' and a['Params']['Controller'] == 'cpuset'
               for a in merged[capacity]['Actions'])
assert 'RealtimePerformance' in aggregates['SCHED_SP_RT_APP']
assert 'MaxIoPriority' in aggregates['SCHED_SP_RT_APP']
assert 'TimerSlackNormal' in aggregates['SCHED_SP_RT_APP']

with tempfile.TemporaryDirectory(prefix='gm8-rt-profiles-') as temporary:
    path = Path(temporary)
    (path / 'check.cpp').write_text(program)
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    str(path / 'check.cpp'), '-o', str(path / 'check')], check=True)
    for profile in cpu_profiles:
        subprocess.run([str(path / 'check'), profile['Actions'][0]['Params']['Path']], check=True)
print('PASS: real RT gates reject zero-budget child groups; root paths permit RT; '
      'Android cpuset/IO/slack preserved; actual empty-profile override removes shared limits')

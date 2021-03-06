import os
import pytest
import docker
import time

from utils import docker_client

@pytest.fixture(scope='session',
                params=['tcp', 'zeromq'])
def docker_compose_files(request, pytestconfig):
    '''
    specify docker-compose.yml if not in tests directory
    '''
    root_dir = os.path.split(os.path.dirname(os.path.realpath(__file__)))[0]
    dc_file = os.path.join(root_dir, 'multi_master', 'docker-compose.yml')
    if request.param == 'tcp':
        dc_file = os.path.join(root_dir, 'multi_master', 'docker-compose-tcp.yml')
    return [dc_file]

@pytest.fixture(scope="function")
def start_multi_master(request, build_image, edit_config, start_container, docker_services):
    for host in ['master1', 'master2', 'minion1']:
        service = host[:-1]
        if service == 'minion':
            start_container(host, cmd=['salt-call', 'test.ping'])
        else:
            start_container(host)
        time.sleep(40)
    yield
    docker_services.shutdown()

def test_multi_master(request, start_multi_master):
    '''
    test multi-master when both masters are running
    '''
    transport = ' '.join([x for x in request.keywords.keys() if x.startswith('test_')]).split('[')[-1].strip(']')
    for master in ['master1', 'master2']:
        salt_host = docker_client(master)
        ret = salt_host.exec_run('salt * test.ping')
        assert ret.exit_code == 0

        # verify we are using correct transport
        ret = salt_host.exec_run('salt * config.get transport')
        assert transport in str(ret.output)

def test_multi_first_master(start_multi_master):
    '''
    test first master stopped and run cmds from second
    '''
    for master in ['master1', 'master2']:
        salt_host = docker_client(master)
        ret = salt_host.exec_run('salt * test.ping')
        assert ret.exit_code == 0

    master1 = docker_client('master1')
    master1.exec_run('pkill salt-master')

    # make sure master is dead
    ret = master1.exec_run('salt * test.ping')
    assert b'Salt request timed out. The master is not responding' in ret.output

    master2 = docker_client('master2')
    ret = master2.exec_run('salt * test.ping')
    assert ret.exit_code == 0

def test_multi_second_master(start_multi_master):
    '''
    test second master stopped
    '''
    for master in ['master1', 'master2']:
        salt_host = docker_client(master)
        ret = salt_host.exec_run('salt * test.ping')
        assert ret.exit_code == 0

    master2 = docker_client('master2')
    master2.exec_run('pkill salt-master')

    # make sure master is dead
    ret = master2.exec_run('salt * test.ping')
    assert b'Salt request timed out. The master is not responding' in ret.output

    master1 = docker_client('master1')
    ret = master1.exec_run('salt * test.ping')
    assert ret.exit_code == 0

def test_multi_first_master_down_startup(start_multi_master):
    '''
    test first master down when minion starts up
    '''
    # stop master1 and then start minion1
    master1 = docker_client('master1')
    master1.exec_run('pkill salt-master')

    # make sure master is dead
    ret = master1.exec_run('salt * test.ping')
    assert b'Salt request timed out. The master is not responding' in ret.output

    minion1 = docker_client('minion1')
    minion1.exec_run('pkill salt-minion')
    minion1.exec_run('salt-minion -d')
    time.sleep(20)

    master2 = docker_client('master2')
    ret = master2.exec_run('salt * test.ping')
    assert ret.exit_code == 0

def test_both_masters_stopped(start_multi_master):
    '''
    test when both masters are stopped on minion startup
    '''
    for host in ['master1', 'master2', 'minion1']:
        salt_host = docker_client(host)
        if 'minion' in host:
            salt_host.exec_run('pkill salt-minion')
        else:
            salt_host.exec_run('pkill salt-master')
            # make sure master is dead
            ret = salt_host.exec_run('salt * test.ping')
            assert b'Salt request timed out. The master is not responding' in ret.output

    # start the minion and let it sit for 5 minutes
    # to make sure it doesnt kill process
    minion1 = docker_client('minion1')
    minion1.exec_run('salt-minion -d')
    time.sleep(300)

    for master in ['master1', 'master2']:
        salt_host = docker_client(master)
        salt_host.exec_run('salt-master -d')

    master1 = docker_client('master1')
    ret = master1.exec_run('salt * test.ping')
    assert ret.exit_code == 0

    master2 = docker_client('master2')
    ret = master2.exec_run('salt * test.ping')
    assert ret.exit_code == 0

def test_one_master_up_on_startup(start_multi_master):
    '''
    test when one master is up when minion starts up
    '''
    for host in ['master2', 'minion1']:
        salt_host = docker_client(host)
        if 'minion' in host:
            salt_host.exec_run('pkill salt-minion')
        else:
            salt_host.exec_run('pkill salt-master')

            # make sure master is dead
            ret = salt_host.exec_run('salt * test.ping')
            assert b'Salt request timed out. The master is not responding' in ret.output

    minion1 = docker_client('minion1')
    minion1.exec_run('salt-minion -d')
    time.sleep(20)

    master1 = docker_client('master1')
    ret = master1.exec_run('salt * test.ping')
    assert ret.exit_code == 0

    master2= docker_client('master2')
    salt_host.exec_run('salt-master -d')
    time.sleep(20)

    ret = master2.exec_run('salt * test.ping')
    assert ret.exit_code == 0

def test_refresh_pillar_masters(start_multi_master):
    '''
    test refreshing pillar when masters are up and
    when only one is up
    '''
    # verify both masters are up and can run refresh
    for master in ['master1', 'master2']:
        salt_host = docker_client(master)
        ret = salt_host.exec_run('salt * saltutil.refresh_pillar')
        assert ret.exit_code == 0

    master1 = docker_client('master1')
    master1.exec_run('pkill salt-master')

    # make sure master is dead
    ret = master1.exec_run('salt * test.ping')
    assert b'Salt request timed out. The master is not responding' in ret.output

    master2= docker_client('master2')
    ret = master2.exec_run('salt * saltutil.refresh_pillar')
    assert ret.exit_code == 0

    master2.exec_run('pkill salt-master')

    # make sure master is dead
    ret = master2.exec_run('salt * test.ping')
    assert b'Salt request timed out. The master is not responding' in ret.output

    master1.exec_run('salt-master -d')
    time.sleep(20)
    ret = master1.exec_run('salt * saltutil.refresh_pillar')
    assert ret.exit_code == 0

def test_masters_down_minion_cmd(start_multi_master):
    '''
    test salt-call when both masters are down
    '''
    for master in ['master1', 'master2']:
        salt_host = docker_client(master)
        ret = salt_host.exec_run('pkill salt-master')
        assert ret.exit_code == 0

    minion1 = docker_client('minion1')
    ret = minion1.exec_run('salt-call test.ping')
    assert b'No master could be reached' in ret.output

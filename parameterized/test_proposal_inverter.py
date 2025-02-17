import pytest

from proposal_inverter import Owner, Broker, ProposalInverter


@pytest.fixture
def inverter():
    owner = Owner()
    owner.funds = 1000
    inverter = owner.deploy(500)

    return inverter


@pytest.fixture
def broker1():
    broker1 = Broker()
    broker1.funds = 100

    return broker1


@pytest.fixture
def broker2():
    broker2 = Broker()
    broker2.funds = 100

    return broker2
    
    
def test_add_broker(inverter, broker1):
    """"
    Simple test to add a single broker and check the properties of the proposal inverter.
    """
    # Add broker to proposal inverter
    broker1 = inverter.add_broker(broker1, 50)

    assert inverter.funds == 550
    assert inverter.number_of_brokers() == 1

    assert broker1.funds == 50


def test_claim_broker_funds(inverter, broker1, broker2):
    """
    Test that the brokers receive the correct amounts of funds when they claim their funds before the minimum number of
    epochs.
    """
    # Add broker to proposal inverter
    broker1 = inverter.add_broker(broker1, 50)

    # Make a claim before the minimum number of epochs
    inverter.iter_epoch(10)

    broker1 = inverter.claim_broker_funds(broker1)

    assert inverter.funds == 450
    assert broker1.funds == 150

    # Add a second broker
    broker2 = inverter.add_broker(broker2, 50)

    # Make a claim before the minimum number of epochs
    inverter.iter_epoch(10)

    broker2 = inverter.claim_broker_funds(broker2)

    assert inverter.funds == 450
    assert broker2.funds == 100

    # Make a claim after the minimum number of epochs
    inverter.iter_epoch(10)

    broker1 = inverter.claim_broker_funds(broker1)

    assert inverter.funds == 350
    assert broker1.funds == 250

    
def test_remove_broker(inverter, broker1, broker2):
    """
    Ensure that when a broker leaves the proposal inverter, they receive their stake if they have stayed for the minimum
    number of epochs.
    """
    # Add brokers
    broker1 = inverter.add_broker(broker1, 100)
    broker2 = inverter.add_broker(broker2, 100)

    assert inverter.number_of_brokers() == 2
    assert inverter.funds == 700

    inverter.iter_epoch(20)

    broker1 = inverter.remove_broker(broker1)

    assert inverter.number_of_brokers() == 1
    assert inverter.funds == 600
    assert broker1.funds == 100

    # Remove a broker while over the minimum number of epochs
    inverter.iter_epoch(10)

    broker2 = inverter.remove_broker(broker2)

    assert inverter.number_of_brokers() == 0
    assert inverter.funds == 300
    assert broker2.funds == 300

    
def test_get_allocated_funds(inverter, broker1, broker2):
    assert inverter.get_allocated_funds() == 0

    # Add broker
    broker1 = inverter.add_broker(broker1, 100)

    # Add a second broker
    inverter.iter_epoch(10)

    broker2 = inverter.add_broker(broker2, 100)

    assert inverter.funds == 700
    assert inverter.number_of_brokers() == 2
    assert inverter.get_allocated_funds() == 100

    inverter.iter_epoch(20)

    assert inverter.get_allocated_funds() == 300


def test_pay(inverter, broker1):
    broker1 = inverter.pay(broker1, 25)

    assert broker1.funds == 75
    assert inverter.funds == 525

    
def test_cancel(inverter, broker1, broker2):
    # Add brokers (each with a different initial stake)
    broker1 = inverter.add_broker(broker1, 50)
    broker2 = inverter.add_broker(broker2, 100)
    
    # Check total funds: 500(owner initial amount) + 50 (broker1 stake) + 100 (broker2 stake)
    assert inverter.funds == 650
    
    inverter.iter_epoch(30)
    
    # Cancel the proposal inverter
    inverter.cancel()

    # Each broker makes their claim
    broker1 = inverter.claim_broker_funds(broker1)
    broker2 = inverter.claim_broker_funds(broker2)
        
    # Broker1 funds = 300 + 50(broker1's current funds)
    assert broker1.funds == 350
    
    # Broker2 funds = 350 + 0(broker2's current funds)
    assert broker2.funds == 350

    # End state of proposal inverter
    assert inverter.funds == 0
    assert inverter.get_allocated_funds() == 0

    
def test_forced_cancel_case1(broker1):
    """
    First test case involves using an inverter where the minimum number of brokers is 2. If only one broker joins and
    the minimum horizon is reached, then the forced cancel should be triggered and all remaining funds should be
    allocated to the single broker in the inverter.
    """
    # Deploy proposal inverter
    owner = Owner()
    owner.funds = 1000
    inverter = owner.deploy(100, min_brokers=2)

    # Add broker
    broker1 = inverter.add_broker(broker1, 10)

    # Iterate past the buffer period to trigger the forced cancel
    inverter.iter_epoch(10)

    assert inverter.number_of_brokers() < inverter.min_brokers
    assert inverter.get_horizon() < inverter.min_horizon
    assert inverter.get_allocated_funds() == inverter.funds


def test_forced_cancel_case2(broker1):
    """
    Second test case occurs when the inverter is below the minimum horizon and all brokers leave. In this case, there
    are no brokers to allocate the funds to, so when the forced cancel is triggered, all funds should be returned to the
    owner.
    """
    # Deploy proposal inverter
    owner = Owner()
    owner.funds = 1000
    inverter = owner.deploy(100)
    
    # Add broker
    broker1 = inverter.add_broker(broker1, 9)

    # Dip below the minimum conditions
    inverter.iter_epoch(5)

    broker1 = inverter.remove_broker(broker1)

    # Iterate past the buffer period
    inverter.iter_epoch(6)

    assert inverter.number_of_brokers() < inverter.min_brokers
    assert inverter.get_horizon() < inverter.min_horizon
    assert inverter.get_allocated_funds() == inverter.funds


def test_forced_cancel_case3(broker1, broker2):
    """
    Third test case is to ensure the forced cancel counter resets if the inverter is no longer under the minimum
    conditions. The inverter dips below the minimum conditions for a few epochs less than the specified buffer period,
    and the goes back up. The counter should reset, and then the inverter should dip back down and trigger the forced
    cancel.
    """
    # Deploy proposal inverter
    owner = Owner()
    owner.funds = 1000
    inverter = owner.deploy(100, min_brokers=2)

    # Add brokers
    broker1 = inverter.add_broker(broker1, 10)

    # Dip below minimum conditions but before the forced cancel triggers
    inverter.iter_epoch(6)

    assert inverter.number_of_brokers() < inverter.min_brokers
    assert inverter.get_horizon() < inverter.min_horizon
    assert inverter.get_allocated_funds() < inverter.funds

    # Add a second broker and funds to meet the minimum conditions again
    broker2 = inverter.add_broker(broker2, 60)

    assert inverter.number_of_brokers() >= inverter.min_brokers
    assert inverter.get_horizon() >= inverter.min_horizon

    # Dip below minimum conditions and trigger the forced cancel
    broker1 = inverter.remove_broker(broker1)

    inverter.iter_epoch(6)

    assert inverter.number_of_brokers() < inverter.min_brokers
    assert inverter.get_horizon() < inverter.min_horizon
    assert inverter.get_allocated_funds() < inverter.funds

    inverter.iter_epoch(4)

    assert inverter.get_allocated_funds() == inverter.funds


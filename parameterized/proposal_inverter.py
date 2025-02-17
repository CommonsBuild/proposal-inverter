import param as pm
import panel as pn
from eth_account import Account
import secrets
pn.extension()


def generate_eth_account():
    priv = secrets.token_hex(32)
    private = "0x" + priv
    public = Account.from_key(private).address
    return (private, public)


class Wallet(pm.Parameterized):
    funds = pm.Number(100)
    def __init__(self, **params):
        super(Wallet, self).__init__(**params)
        (private, public) = generate_eth_account()
        self.private = private
        self.public = public
        
        
class Broker(Wallet):
    pass


class BrokerAgreement(pm.Parameterized):
    """
    Stores data about a broker in the proposal inverter.
    """
    epoch_joined = pm.Number(0, constant=True, doc="epoch at which this broker joined")
    initial_stake = pm.Number(0, constant=True, doc="total funds staked")
    allocated_funds = pm.Number(0, doc="total funds that the broker can currently claim")
    total_claimed = pm.Number(0, doc="total funds the broker has claimed thus far")


class ProposalInverter(Wallet):
    # State
    
    # Parameters
    min_stake = pm.Number(5, doc="minimum funds that a broker must stake to join")
    current_epoch = pm.Number(0, doc="number of epochs that have passed")
    cancel_epoch = pm.Number(0, doc="last epoch where minimum conditions were been met")
    epoch_length = pm.Number(60*60*24, doc="length of one epoch, measured in seconds")
    min_epochs = pm.Number(28, doc="minimum number of epochs that must pass for a broker to exit and take their stake")
    allocation_per_epoch = pm.Number(10, doc="funds allocated to all brokers per epoch")
    min_horizon = pm.Number(7, doc="minimum number of future epochs the proposal inverter can allocate funds for")
    min_brokers = pm.Number(1, doc="minimum number of brokers required to continue")
    max_brokers = pm.Number(5, doc="maximum number of brokers that can join")
    buffer_period = pm.Number(5, doc="minimum number of epochs for a condition to trigger the cancellation of the proposal inverter")
    broker_agreements = pm.Dict(dict(), doc="maps each broker's public key to their broker agreement")
    
    def __init__(self, owner: Wallet, initial_funds: float, **params):
        super(ProposalInverter, self).__init__(**params)
        self.owner_address = owner.public
        if owner.funds >= initial_funds:
            owner.funds -= initial_funds
            self.funds = initial_funds

        self.committed_brokers = set()
    
    def add_broker(self, broker: Broker, stake: float):
        """
        A broker can join the agreement (and must also join the stream associated with that agreement) by staking the
        minimum stake.
        
        Note that if the act of joining would cause |B+|>nmax then joining would fail. It is not possible for more than
        `n_max` brokers to be party to this agreement.

        Furthermore, it is possible to enforce addition access control via whitelists or blacklists which serve to
        restrict access to the set of brokers. These lists may be managed by the owner, the payers, and/or the brokers;
        however, scoping an addition access control scheme is out of scope at this time.
        """
        if broker.public in self.broker_agreements.keys():
            print("Failed to add broker, broker already has a stake in this proposal")
        elif len(self.committed_brokers) + 1 > self.max_brokers:
            print("Failed to add broker, maximum number of brokers reached")
        elif stake < self.min_stake:
            print("Failed to add broker, minimum stake not met")
        else:
            broker.funds -= stake
            self.funds += stake
            self.broker_agreements[broker.public] = BrokerAgreement(
                epoch_joined=self.current_epoch,
                initial_stake=stake,
                allocated_funds=0,
                total_claimed=0
            )
            self.committed_brokers.add(broker)

        return broker

    def claim_broker_funds(self, broker: Broker):
        """
        A broker that is attached to an agreement can claim their accumulated rewards at their discretion.

        Note that while this decreases the total funds in the contract it does not decrease the unallocated (remaining)
        funds in the conract because claims only extract claims according to a deterministic rule computed over the past.

        Many brokers may choose to claim their funds more or less often depending on opportunity costs and gas costs.

        Preferred implementations may vary – see section on synthetics state.
        """
        broker_agreement = self.broker_agreements.get(broker.public)

        if broker_agreement is None:
            print("Broker is not part of this proposal, no funds are claimed")
        else:
            # Possible to claim a custom amount and default to maximum?
            claim = broker_agreement.allocated_funds

            broker_agreement.allocated_funds = 0
            broker_agreement.total_claimed += claim
            broker.funds += claim
            self.funds -= claim

        return broker

    def remove_broker(self, broker: Broker):
        """
        In the event that the horizon is below the threshold or a broker has been attached to the agreement for more than
        the minimum epochs, a broker may exit an agreement and take their stake (and outstanding claims).

        However if a broker has not stayed for the entire period, or the contract is not running low on funds, the stake
        will be kept as payment by the agreement contract when the broker leaves.

        In a more extreme case we may require the broker to relinquish the claim as well but this would easily be skirted
        by making a claim action before leaving.
        """
        broker_agreement = self.broker_agreements.get(broker.public)

        if broker_agreement is None:
            print("Broker is not part of this proposal")
        else:
            if self.current_epoch - broker_agreement.epoch_joined >= self.min_epochs:
                stake = broker_agreement.initial_stake
                broker.funds += stake
                self.funds -= stake

            broker = self.claim_broker_funds(broker)
            del self.broker_agreements[broker.public]
            self.committed_brokers.remove(broker)

        return broker

    def iter_epoch(self, n_epochs=1):
        """
        Iterates to the next epoch and updates the total claimable funds for each broker.

        There may conditions under which any address may trigger the cancel but these conditions should be 
        indicative of a failure on the part of the payer. An example policy would be to allow forced cancel 
        when n < nmin and H < H min, and possibly only if this is the case more multiple epochs.
        """
        for epoch in range(n_epochs):
            for public, broker_agreement in self.broker_agreements.items():
                broker_agreement.allocated_funds += self.get_broker_claimable_funds()

            # Use cancel_epoch to record when the cancellation condition was triggered
            if self.number_of_brokers() >= self.min_brokers or self.get_horizon() >= self.min_horizon:
                self.cancel_epoch = self.current_epoch

            # If the forced cancellation conditions are met for a period longer than the buffer period, trigger the cancel function
            if (self.current_epoch - self.cancel_epoch) > self.buffer_period:
                self.cancel()

            self.current_epoch += 1

    def number_of_brokers(self):
        return len(self.committed_brokers)
    
    def get_broker_claimable_funds(self):
        return self.allocation_per_epoch / self.number_of_brokers()
    
    def get_allocated_funds(self):
        """
        Returns the total unclaimed allocated funds from all broker agreements.
        """
        return sum([broker_agreement.allocated_funds for broker_agreement in self.broker_agreements.values()])

    def get_horizon(self):
        """
        Returns the current horizon.
        """
        return (self.funds - self.get_allocated_funds()) / self.allocation_per_epoch
    
    def pay(self, broker: Broker, tokens):
        """
        A payer takes the action pay by providing a quantity of tokens (split into Stablecoins and DAO tokens) 
        ΔF, which increased the unallocated funds (and thus also the total funds).
        F+ = F + ΔF
        R+ = R + ΔF
        Furthermore, the Horizon H is increased 
        H+ = (R + ΔF)/ ΔA = H + (ΔF/ΔA)
        """
        broker.funds -= tokens
        self.funds += tokens
        return broker
    
    def cancel(self):
        """
        In the event that the owner closes down a contract, each Broker gets back their stake, and recieves any 
        unclaimed tokens allocated to their address as well an equal share of the remaining unallocated assets.
        
        That is to say the quantity Δdi of data tokens is distributed to each broker i∈B

        Δdi=si+ai+RN

        and thus the penultimate financial state of the contract is

        S=0R=0A=0

        when the contract is self-destructed.
        """    
        total_stake = sum([broker_agreement.initial_stake for broker_agreement in self.broker_agreements.values()])
        total_allocated_funds = self.get_allocated_funds()

        for public_key, broker_agreement in self.broker_agreements.items():
            broker_agreement.allocated_funds += broker_agreement.initial_stake + (self.funds - total_stake - total_allocated_funds) / self.number_of_brokers()

        # If there are no brokers attached to the proposal inverter, return funds to owner
        self.broker_agreements[self.owner_address] = BrokerAgreement(
            epoch_joined=self.current_epoch,
            initial_stake=0,
            allocated_funds=self.funds - self.get_allocated_funds(),
            total_claimed=0           
        )
    
    
class Owner(Wallet):
    def _default_agreement_contract_params(self):
        params = dict(
            min_stake = 5,
            epoch_length = 60*60*24,
            min_epochs = 28,
            allocation_per_epoch = 10,
            min_horizon = 7,
            min_brokers = 1,
            max_brokers = 5,
        )
        return params
    
    def deploy(self, initial_funds, **agreement_contract_params):
        """
        An actor within the ecosystem can deploy a new agreement contract by specifying which proposal the agreement 
        supports, setting the parameters of the smart contract providing initial funds, and providing any (unenforced) 
        commitment to continue topping up the contract as payer under as long as a set of SLAs are met. For the purpose 
        of this draft, it is assumed that the contract is initialized with some quantity of funds F such that H>Hmin 
        and that B=∅.
        """
        params = self._default_agreement_contract_params()
        params.update(agreement_contract_params)
            
        # Check imposed restrictions (whether horizon is greater than the min horizon)
        horizon = initial_funds / params['allocation_per_epoch']
        if horizon < params['min_horizon']:
            print("The Horizon is lower than the mininum required horizon")
            return None

        agreement_contract = ProposalInverter(
                owner = self,
                initial_funds = initial_funds,
                **params,
            )
        
        return agreement_contract
        
    def cancel(self, agreement_contract, broker_pool):
        """
        In the event that the owner closes down a contract, each Broker gets back their stake, and recieves any 
        unclaimed tokens allocated to their address as well an equal share of the remaining unallocated assets.
        
        That is to say the quantity Δdi of data tokens is distributed to each broker i∈B
        Δdi=si+ai+(R/N)
        and thus the penultimate financial state of the contract is
        S=0, R=0, A=0
        when the contract is self-destructed.
        """
        # This function relies on there being given a broker_pool that keeps track of brokers
        
        # Calculate the total allocated funds & total stake for proper calculation
        agreement_contract.cancel()

        for broker_key in broker_pool:
            broker_pool[broker_key] = agreement_contract.claim_broker_funds(broker_pool[broker_key])

        return broker_pool


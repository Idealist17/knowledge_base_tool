// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Small ETH staking vault with timestamp-based rewards.
contract VaultRewards {
    address public owner;
    uint256 public totalDeposits;
    uint256 public rewardRatePerSecond;

    mapping(address => uint256) public balanceOf;
    mapping(address => uint256) public lastRewardTime;
    mapping(address => uint256) public pendingRewards;

    event Deposited(address indexed user, uint256 amount);
    event Withdrawn(address indexed user, uint256 amount);
    event RewardClaimed(address indexed user, uint256 amount);
    event RewardRateUpdated(uint256 oldRate, uint256 newRate);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor(uint256 initialRewardRate) {
        owner = msg.sender;
        rewardRatePerSecond = initialRewardRate;
    }

    function deposit() external payable {
        require(msg.value > 0, "zero deposit");
        _checkpoint(msg.sender);
        balanceOf[msg.sender] += msg.value;
        totalDeposits += msg.value;
        emit Deposited(msg.sender, msg.value);
    }

    function withdraw(uint256 amount) external {
        require(amount > 0, "zero withdraw");
        require(balanceOf[msg.sender] >= amount, "insufficient balance");
        _checkpoint(msg.sender);
        balanceOf[msg.sender] -= amount;
        totalDeposits -= amount;
        payable(msg.sender).transfer(amount);
        emit Withdrawn(msg.sender, amount);
    }

    function claim() external returns (uint256 reward) {
        _checkpoint(msg.sender);
        reward = pendingRewards[msg.sender];
        require(reward > 0, "no reward");
        pendingRewards[msg.sender] = 0;
        payable(msg.sender).transfer(reward);
        emit RewardClaimed(msg.sender, reward);
    }

    function setRewardRate(uint256 newRate) external onlyOwner {
        emit RewardRateUpdated(rewardRatePerSecond, newRate);
        rewardRatePerSecond = newRate;
    }

    function previewReward(address user) external view returns (uint256) {
        return pendingRewards[user] + _accrued(user);
    }

    function _checkpoint(address user) internal {
        pendingRewards[user] += _accrued(user);
        lastRewardTime[user] = block.timestamp;
    }

    function _accrued(address user) internal view returns (uint256) {
        uint256 balance = balanceOf[user];
        if (balance == 0) {
            return 0;
        }
        uint256 elapsed = block.timestamp - lastRewardTime[user];
        return elapsed * balance * rewardRatePerSecond / 1 ether;
    }
}

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Vault {
    mapping(address => uint256) public balance;

    function deposit() external payable {
        balance[msg.sender] += msg.value;
    }

    function withdraw(uint256 amount) external {
        require(balance[msg.sender] >= amount, "bal");
        balance[msg.sender] -= amount;
        payable(msg.sender).transfer(amount);
    }
}

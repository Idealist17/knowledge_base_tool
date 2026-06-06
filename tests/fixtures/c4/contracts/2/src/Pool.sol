// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract Pool {
    mapping(address => uint256) public shares;
    function join() external payable { shares[msg.sender] += msg.value; }
    function exit(uint256 amount) external {
        require(shares[msg.sender] >= amount, "shares");
        (bool ok,) = msg.sender.call{value: amount}("");
        require(ok, "send");
        shares[msg.sender] -= amount;
    }
}

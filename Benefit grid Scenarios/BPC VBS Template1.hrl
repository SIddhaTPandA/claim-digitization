benefit plan component
name "BPC VBS Template1"
description "BPC VBS Template1"
internal definition
in network tier definition
name "Preferred Providers"
benefits
benefit for billed on professional claim and (place of service "11", "12") and (service category "Office Visits", "Emergency Room Facility Fees", "Immunizations") and not (service category "Office Visit Specialist", "Emergency room services", "Urgent care") is "Imaging Coins-INN"% of service cost with a copay of "Imaging Copay-INN" per day deductible waived requires review use review message "Claim needs to be reviewed for benefit provision" benefit label "Imaging Coins-INN",
benefit for (service category "Emergency Room Facility Fees " and service category " Office Visits " and service category " Immunizations") is 90% of service cost 
for all other services benefit is "Default Coins-INN"% of service cost requires review use review message "Claim needs to be reviewed for benefit provision" benefit label "Default Coins-INN",
in network tier definition
name "Preferred Providers Tier B"
benefits
benefit for (service category "Ambulatory Surgery " and service category " Urgent care " and service category " Emergency room services") and not (service category "Ambulatory Surgery" and service category "Urgent care" and service category "Emergency room services") is "Ambulatory Surgery Coin INN"% of service cost,
benefit for billed on professional claim and place of service "11" and  service category  "Immunizations" is 100% of service cost  with a copay of $30  per day deductible waived requires review use review message "Claim needs to be reviewed for benefit provision"
for all other services benefit is 90% of service cost  requires review use review message "Claim needs to be reviewed for benefit provision" benefit label "Default Coins-Tier B"
out of network tier definition
benefits
benefit for (service category "Emergency Room Facility Fees " and service category " Office Visits " and service category " Immunizations") is 90% of service cost ,
benefit for billed on professional claim and (place of service "11", "12") and (service category "Office Visits", "Emergency Room Facility Fees", "Immunizations") and not (service category "Office Visit Specialist", "Emergency room services", "Urgent care") is "Imaging Coins-INN"% of service cost with a copay of "Imaging Copay-INN" per day deductible waived requires review use review message "Claim needs to be reviewed for benefit provision" benefit label "Imaging Coins-INN"
for all other services benefit is "Default Coins-OON"% of service cost benefit label "Default Coins-OON"
out of area tier definition
benefits
benefit for (place of service "12", "11", "10", "22", "21", "23", "20", "11", "23", "24") and (service category "Immunizations", "Ambulatory Surgery") is "Immunization Coins-INN"% of service cost use message "Altered claim/corrective material used",
benefit for billed on professional claim and place of service "11" and  service category  "Immunizations" and not (service category "Emergency Room Facility Fees", "Ambulatory Surgery", "Immunizations") is "Vision Coins-INN"% of service cost benefit label "Vision Coins-INN"
for all other services benefit is 100% of service cost  requires review use review message "Claim needs to be reviewed for fee provision" benefit label "Default Coins-OOA"

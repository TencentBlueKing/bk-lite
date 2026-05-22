## ADDED Requirements

### Requirement: Expired `admin` account password enters forced reset flow during username/password login
When the account whose username is `admin` logs in with correct username and password and the password is expired, the system SHALL require password reset before allowing access to the product instead of hard-failing the login.

#### Scenario: Expired `admin` account password on main login page
- **WHEN** the user whose username is `admin` submits correct username and password on the main web login page
- **AND** the user's password is expired according to `pwd_set_validity_period`
- **THEN** the system SHALL continue into the existing forced password reset flow
- **AND** the user SHALL be required to enter a new password before product access is granted

#### Scenario: Expired `admin` account password on re-login window
- **WHEN** the user whose username is `admin` submits correct username and password in the session-expired re-login window
- **AND** the user's password is expired according to `pwd_set_validity_period`
- **THEN** the system SHALL continue into the existing forced password reset flow
- **AND** the user SHALL be required to enter a new password before product access is granted

#### Scenario: Password reset not completed
- **WHEN** the user whose username is `admin` has entered the forced password reset flow because the password is expired
- **AND** the user has not successfully completed password reset yet
- **THEN** the system SHALL continue preventing access to product pages

### Requirement: Non-`admin` expired-password behavior remains unchanged
The system SHALL keep existing expired-password behavior for every account whose username is not `admin`.

#### Scenario: Expired non-`admin` password
- **WHEN** a user whose username is not `admin` submits correct username and password
- **AND** the user's password is expired according to `pwd_set_validity_period`
- **THEN** the system SHALL reject the login with the existing expired-password failure behavior

### Requirement: This change is scoped to Web login entry points only
This change SHALL document and guarantee behavior only for the main Web login page and the session-expired re-login window. Mobile handling remains out of scope and unchanged in this iteration.

#### Scenario: Mobile client behavior
- **WHEN** the Mobile client uses the same backend login API
- **THEN** this change SHALL NOT be interpreted as requiring Mobile-specific reset-flow updates
- **AND** Mobile behavior SHALL remain outside the implementation scope of this change

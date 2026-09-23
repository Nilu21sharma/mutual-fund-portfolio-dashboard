/* =====================================================================
   Step 1: Create the database and the 3 main tables
   Server : NILU (Windows Authentication)
   Run    : sqlcmd -S NILU -E -i sql\01_create_database.sql
            (or open this file in SSMS and press F5)
   Safe to run again: it only creates things that don't exist yet.
   ===================================================================== */

-- 1) Create the database
IF DB_ID('MFPortfolioDB') IS NULL
    CREATE DATABASE MFPortfolioDB;
GO

USE MFPortfolioDB;
GO

/* ---------------------------------------------------------------------
   2) FundMaster: one row per mutual fund scheme you want to track.
      SchemeCode = the AMFI code. It links the NAV data to your funds.
   --------------------------------------------------------------------- */
IF OBJECT_ID('dbo.FundMaster', 'U') IS NULL
CREATE TABLE dbo.FundMaster (
    FundID          INT IDENTITY(1,1) PRIMARY KEY,
    SchemeCode      INT            NOT NULL UNIQUE,
    SchemeName      NVARCHAR(300)  NOT NULL,
    AMC             NVARCHAR(150)  NULL,      -- fund house, e.g. "HDFC Mutual Fund"
    Category        NVARCHAR(150)  NULL,      -- e.g. "Equity Scheme - Large Cap Fund"
    BuyThresholdPct DECIMAL(5,2)   NOT NULL DEFAULT (-3.00), -- signal "BUY" when NAV falls this % below month-start
    IsActive        BIT            NOT NULL DEFAULT (1),     -- 0 = stop tracking
    CreatedAt       DATETIME2(0)   NOT NULL DEFAULT (SYSDATETIME())
);
GO

/* ---------------------------------------------------------------------
   3) NAVHistory: one NAV per fund per day.
      The UNIQUE rule stops the same day from being loaded twice.
   --------------------------------------------------------------------- */
IF OBJECT_ID('dbo.NAVHistory', 'U') IS NULL
CREATE TABLE dbo.NAVHistory (
    NAVID     BIGINT IDENTITY(1,1) PRIMARY KEY,
    FundID    INT            NOT NULL REFERENCES dbo.FundMaster(FundID),
    NAVDate   DATE           NOT NULL,
    NAV       DECIMAL(18,4)  NOT NULL,
    LoadedAt  DATETIME2(0)   NOT NULL DEFAULT (SYSDATETIME()),
    CONSTRAINT UQ_NAVHistory_Fund_Date UNIQUE (FundID, NAVDate)
);
GO

/* ---------------------------------------------------------------------
   4) Transactions: your own buys and sells.
      Units = Amount / NAV on the transaction date.
   --------------------------------------------------------------------- */
IF OBJECT_ID('dbo.Transactions', 'U') IS NULL
CREATE TABLE dbo.Transactions (
    TransactionID INT IDENTITY(1,1) PRIMARY KEY,
    FundID        INT            NOT NULL REFERENCES dbo.FundMaster(FundID),
    TxnDate       DATE           NOT NULL,
    TxnType       VARCHAR(4)     NOT NULL CHECK (TxnType IN ('BUY', 'SELL')),
    Amount        DECIMAL(18,2)  NOT NULL CHECK (Amount > 0),
    NAV           DECIMAL(18,4)  NOT NULL CHECK (NAV > 0),
    Units         DECIMAL(18,4)  NOT NULL CHECK (Units > 0),
    Notes         NVARCHAR(300)  NULL,
    CreatedAt     DATETIME2(0)   NOT NULL DEFAULT (SYSDATETIME())
);
GO

PRINT 'Step 1 done: MFPortfolioDB with FundMaster, NAVHistory, Transactions is ready.';
GO

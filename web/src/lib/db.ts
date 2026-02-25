import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

// Always cache on global — avoids creating a new connection pool on every
// cold-start module re-evaluation (matters on Render free tier).
if (!globalForPrisma.prisma) {
  globalForPrisma.prisma = new PrismaClient({
    log: process.env.NODE_ENV === "development" ? ["query"] : [],
  });
}

export const prisma = globalForPrisma.prisma;


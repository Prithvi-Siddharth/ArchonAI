/** Matching service names to the official AWS icons, and the icon files themselves. */
import { describe, expect, it } from 'vitest'

import { REAL_ARCHITECTURE_BACKWARD, REAL_ARCHITECTURE_COMBINED } from '@/test/real-architectures'

import { ICON_KEYS, iconForPart, iconsFor, normalise, splitServiceName } from './aws-icons'
import { ICON_SVGS } from './icon-svgs'

const keys = (name: string) => iconsFor(name).map((icon) => icon.key)

describe('icon files', () => {
  it('every mapped icon has its official SVG, and no file is unused', () => {
    expect(ICON_KEYS.filter((key) => !ICON_SVGS.has(key))).toEqual([])
    expect([...ICON_SVGS.keys()].filter((key) => !ICON_KEYS.includes(key))).toEqual([])
  })

  it('each file is an official AWS service icon (its Arch_..._64 id, 80 x 80 view box)', () => {
    for (const [key, svg] of ICON_SVGS) {
      expect(svg.startsWith('<svg'), key).toBe(true)
      expect(svg, key).toContain('viewBox="0 0 80 80"')
      expect(svg, key).toMatch(/id="Icon-Architecture\/64\/Arch_[^"]+_64"/)
    }
  })
})

describe('name matching', () => {
  it('splits combined names into their parts', () => {
    expect(splitServiceName('Amazon ECS (Fargate) + Auto Scaling + AWS Lambda')).toEqual(['Amazon ECS', 'Fargate', 'Auto Scaling', 'AWS Lambda'])
    expect(splitServiceName('DynamoDB / ElastiCache, S3 & SQS')).toEqual(['DynamoDB', 'ElastiCache', 'S3', 'SQS'])
    expect(normalise('Amazon Aurora PostgreSQL')).toBe('aurorapostgresql')
  })

  it.each([
    ['Amazon CloudFront + AWS WAF', ['cloudfront', 'waf']],
    ['Amazon ECS (Fargate) + Auto Scaling + AWS Lambda', ['ecs', 'fargate', 'ec2-auto-scaling', 'lambda']],
    ['AWS CloudTrail + KMS + Secrets Manager', ['cloudtrail', 'kms', 'secrets-manager']],
    ['Amazon Aurora PostgreSQL', ['aurora']],
    ['Amazon DynamoDB + Aurora PITR', ['dynamodb', 'aurora']],
    ['Application Load Balancer', ['elastic-load-balancing']],
    ['Route 53 + ALB', ['route-53', 'elastic-load-balancing']],
    ['Amazon ElastiCache (Redis)', ['elasticache']],
    ['Amazon S3', ['s3']],
    ['Amazon S3 Glacier', ['s3-glacier']],
    ['Amazon MQ', ['mq']],
    ['CloudWatch Logs', ['cloudwatch']],
    ['AWS IAM Identity Center', ['iam-identity-center']],
  ])('%s', (name, expected) => {
    expect(keys(name)).toEqual(expected)
  })

  it.each(['User browser', 'Third-party payment gateway', 'Mobile clients', 'MQTT broker', 'Redis', ''])('no guessed icon for "%s"', (name) => {
    expect(keys(name)).toEqual([])
  })

  it('a short alias matches only exactly, never as the start of another word', () => {
    expect(iconForPart('MQTT')).toBeNull()
    expect(iconForPart('S3x')).toBeNull()
  })

  it('every service in the real stored architectures gets at least one official icon', () => {
    for (const service of [...REAL_ARCHITECTURE_COMBINED.services, ...REAL_ARCHITECTURE_BACKWARD.services]) {
      expect(iconsFor(service.name).length, service.name).toBeGreaterThan(0)
    }
  })

  it('caps the number of icons', () => {
    expect(iconsFor('S3 + SQS + SNS + Lambda + ECS', 3)).toHaveLength(3)
  })
})
